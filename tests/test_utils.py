import os
from typing import Dict, List, Optional
from fastmcp import Client
from litellm import aresponses
import logging
import json
from dotenv import load_dotenv
from pathlib import Path
import re

import litellm
litellm.enable_json_schema_validation = True

logger = logging.getLogger(__name__)

## set ENV variables
source_env = Path(__file__).resolve().parent
load_dotenv(source_env / ".env") # Load LLM API keys
load_dotenv(source_env / ".test.env") # Load test project API keys and test resource IDs

class FakeAgentJobContext:
    
    def __init__(self, input: List[Dict]):
        self.input = input.copy()
        self.lastStepModelResponses = []
        self.step = 1

    def appendInput(self, input: Dict):
        self.input.append(input)

    def getInput(self) -> List[Dict]:
        return self.input.copy()

    def getLastStepModelResponses(self) -> List[Dict]:
        return self.lastStepModelResponses

    def persistLastStepModelResponses(self, responses: List[Dict]):
        self.lastStepModelResponses = responses

    def incrementStep(self):
        self.step += 1

def mcp_tools_to_openai_tools(tools):
    out = []
    for tool in tools:
        out.append({
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.inputSchema,
        })
    return out
class FakeAgent:
    """
    A minimal single-model adapter that pretends to plan tool calls in sequence.
    Deterministic behavior tailored for the example scenario in fake-agent-test-engine.md.
    """

    def __init__(self, apiBaseUrl: str, appId: str, appToken: str, model: str, serverPath: str):
        self.apiBaseUrl = apiBaseUrl
        self.appId = appId
        self.appToken = appToken
        self.model = model
        self._current_goal: Optional[str] = None
        self._stage: int = 0
        self.mcpClient = None;
        self.tools = None;
        self.mcpConfig = None;
        self.serverPath = serverPath

    async def initialize(self):
        # Discover tools from local server
        server_path = os.path.join(os.path.dirname(__file__), "..", self.serverPath)
        server_path = os.path.abspath(server_path)

        self.mcpConfig = {
            "mcpServers": {
                "local_server": {
                    "transport": "stdio",
                    "command": "uv",
                    "args": ["run", "python", server_path, "--transport", "stdio"],
                    "env": {
                        "DEBUG": "true",
                        "VOUCHERIFY_APP_ID": self.appId, 
                        "VOUCHERIFY_APP_TOKEN": self.appToken,
                        "VOUCHERIFY_API_BASE_URL": self.apiBaseUrl
                    }
                }
            }
        }

        self.mcpClient = Client(self.mcpConfig)
        async with self.mcpClient:
            # Basic server interaction
            await self.mcpClient.ping()
            self.tools = await self.mcpClient.list_tools()
            logger.info("MCP Tools: ")
            logger.info(json.dumps(mcp_tools_to_openai_tools(self.tools), indent=4))

    async def callModel (self, jobContext: FakeAgentJobContext) -> FakeAgentJobContext:
        response = await aresponses(
            model = self.model, 
            input= jobContext.getInput(),    
            tools = mcp_tools_to_openai_tools(self.tools),
            # store=False # must be true to be able to send back `reasoning`
        )
        logger.info("[FakeAgent] (Step %s) Model Response:", jobContext.step)
        modelResponse = response.model_dump()
        del modelResponse["tools"] # it returns tools list, removing for cleaner logging
        logger.info(json.dumps(modelResponse, indent=4))

        givenStepModelResponses = []

        for i, output in enumerate(response.output, start=0):
            nextInput = output.model_dump()
            del nextInput["status"]
            jobContext.appendInput(nextInput) 
            
            if output.type == "reasoning": # OpenAPI specific
                continue
            elif output.type == "message":
                logger.info("[FakeAgent] (Step %s-%s) Model sent message: %s", jobContext.step, i, output.content[0].text)
                givenStepModelResponses.append({
                    "type": "message",
                    "content": output.content[0].text,
                    "has_more": len(output.content) > 1
                })
            elif output.type == "function_call":
                logger.info("[FakeAgent] (Step %s-%s) Models wants to call tool '%s' with arguments '%s'", jobContext.step, i, output.name, output.arguments)

                mcpClient = Client(self.mcpConfig)
                async with mcpClient:
                    try:
                        toolResponse = await mcpClient.call_tool(output.name, json.loads(output.arguments))
                        logger.info("[FakeAgent] (Step %s-%s) MCP Response: %s", jobContext.step, i, toolResponse.data)
                        # logger.info(toolResponse)
                        data = toolResponse.data
                    except Exception as error:
                        logger.error("[FakeAgent] (Step %s-%s) MCP Error response: %s", jobContext.step, i, error)
                        data = str(error)

                    givenStepModelResponses.append({
                        "type": "tool_call",
                        "name": output.name,
                        "arguments": json.loads(output.arguments),
                        "output": data,
                    })

                    jobContext.appendInput({
                        "type": "function_call_output",
                        "call_id": output.call_id,
                        "output": data,
                    })
            else:
                raise Exception(f"[FakeAgent] (Step %s-%s) Unsupported output type: {output.type}", jobContext.step, i)

        jobContext.persistLastStepModelResponses(givenStepModelResponses)


    async def startJob(self, prompt: str) -> FakeAgentJobContext:
        systemPrompt = "You are a helpful assistant that can help with answering questions using exposed tools in first place"
        initialInput = [
            { "content": systemPrompt, "role": "system"},
            { "content": prompt, "role": "user"}
        ]
        jobContext = FakeAgentJobContext(initialInput)
        await self.callModel(jobContext)
        return jobContext

    async def advanceJob(self, jobContext: FakeAgentJobContext):
        jobContext.incrementStep()
        await self.callModel(jobContext)


# Custom assertions

def assert_tool_call_count(jobContext: FakeAgentJobContext, expectedToolCount: int) -> None:
    assert len(jobContext.getLastStepModelResponses()) == expectedToolCount, f"(Step: {jobContext.step}) Expected {expectedToolCount} tool invocations, but got: {len(jobContext.getLastStepModelResponses())}"

def assert_tool_call(jobContext: FakeAgentJobContext, expectedToolName: str, expectedToolArgs: Dict, expectedOutput: Optional[Dict] = None) -> None:
    allResponses = jobContext.getLastStepModelResponses()

    lastAssertionError = None
    for lastStep in jobContext.getLastStepModelResponses():
        try:
            lastAssertionError = None
            assert lastStep is not None, f"(Step: {jobContext.step}) Expected tool invocation from the model, but got none"
            assert lastStep["type"] == "tool_call", f"(Step: {jobContext.step}) Model must call a tool, but got: {allResponses}"

            assert lastStep["name"] == expectedToolName, f"(Step: {jobContext.step}) Expected tool name to be called {expectedToolName}"
            assert lastStep["arguments"] == expectedToolArgs, f"(Step: {jobContext.step}) Expected tool '{expectedToolName}' to be called with arguments {expectedToolArgs}"
            if expectedOutput is not None:
                assert lastStep["output"] == expectedOutput, f"(Step: {jobContext.step}) Expected tool '{expectedToolName}' to return output {expectedOutput}"

            return # one element from the list matched all assertions

        except AssertionError as e:
            lastAssertionError = e

    if lastAssertionError is not None:
        logger.info(json.dumps(allResponses, indent=4))
        logger.error(lastAssertionError)
        raise lastAssertionError


def assert_message(jobContext: FakeAgentJobContext, expectedPatterns: list[str | re.Pattern], disallowedPatterns: list[str] = []) -> None:
    lastStep = jobContext.getLastStepModelResponses()
    assert lastStep[0] is not None, f"(Step: {jobContext.step}) Expected message from the model, but got none"
    assert lastStep[0]["type"] == "message", f"(Step: {jobContext.step}) Model must reply with a message, but got: {lastStep[0]}"
    assert len(lastStep) == 1, f"(Step: {jobContext.step}) Expected only one model response, but got more: {lastStep}"

    content = lastStep[0]["content"]
    for pattern in expectedPatterns:
        if isinstance(pattern, str):
            matched = pattern in content
        elif isinstance(pattern, re.Pattern):
            matched = bool(pattern.search(content))
        else:
            matched = str(pattern) in content
        assert matched, f"(Step: {jobContext.step}) Expected message to contain pattern: '{pattern}', but got: {lastStep[0]['content']}"

    for pattern in disallowedPatterns:
        if isinstance(pattern, str):
            matched = pattern in content
        else:
            matched = str(pattern) in content
        assert not matched, f"(Step: {jobContext.step}) Expected message to not contain pattern: '{pattern}', but got: {lastStep[0]['content']}"


