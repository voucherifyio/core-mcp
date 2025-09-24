import os
import re
import pytest
import pytest_asyncio
import logging
from .test_utils import FakeAgent, assert_tool_call, assert_message

logger = logging.getLogger(__name__)

model = "gpt-5"                        # OpenAI
# model = "claude-sonnet-4-20250514"   # Anthropic

@pytest_asyncio.fixture(scope="session")
async def fake_agent():
    agent = FakeAgent(
        apiBaseUrl=os.environ.get("TEST_VOUCHERIFY_API_BASE_URL"),
        appId=os.environ.get("TEST_VOUCHERIFY_APP_ID"),
        appToken=os.environ.get("TEST_VOUCHERIFY_APP_TOKEN"),
        model=model,
        serverPath="src/voucherify_core_mcp/main.py"
    )
    await agent.initialize()
    return agent



@pytest.mark.asyncio
async def test_find_products_by_multiple_filters(fake_agent: FakeAgent):
    job_goal = "Find products where metadata 'category' = 'Burgers' and price > 20$"
    jobContext = await fake_agent.startJob(job_goal)

    assert_tool_call(
        jobContext,
        expectedToolName = "list_products",
        expectedToolArgs = {
            "filters": {
                "metadata.category": { "conditions": { "$is": "Burgers" } },
                "price": { "conditions": { "$more_than": 2000 } }
            }
        }
    )
    await fake_agent.advanceJob(jobContext)

    assert_message(
        jobContext,
        expectedPatterns = [
            os.environ.get("VF_PRODUCT_BURGER_ID_2"),
            os.environ.get("VF_PRODUCT_BURGER_ID_3"),
        ],
        disallowedPatterns = [
            os.environ.get("VF_PRODUCT_BURGER_ID_1"),
        ]

    )
