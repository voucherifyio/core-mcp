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
async def test_list_customers_by_single_metadata_filter(fake_agent: FakeAgent):
    job_goal = "Find all customers whose metadata 'club' equals 'VIP-Warsaw'. Return their ids and emails."
    jobContext = await fake_agent.startJob(job_goal)

    assert_tool_call(
        jobContext,
        expectedToolName = "list_customers",
        expectedToolArgs = {
            "filters": {
                "metadata.club": { "conditions": { "$is": "VIP-Warsaw" } }
            }
        }
    )
    await fake_agent.advanceJob(jobContext)

    assert_message(
        jobContext,
        expectedPatterns = [
            os.environ.get("VF_CUSTOMER_ID_2"),
            os.environ.get("VF_CUSTOMER_ID_3"),
        ],
        disallowedPatterns = [
            os.environ.get("VF_CUSTOMER_ID_1"),
            os.environ.get("VF_CUSTOMER_ID_4"),
        ]
    )


@pytest.mark.asyncio
async def test_list_customers_by_multiple_metadata_filters(fake_agent: FakeAgent):
    job_goal = "Find all customers whose metadata 'foo' equals 'bar' and metadata 'club' equals 'Katowice'. Return their ids."
    jobContext = await fake_agent.startJob(job_goal)

    assert_tool_call(
        jobContext,
        expectedToolName = "list_customers",
        expectedToolArgs = {
            "filters": {
                "metadata.foo": { "conditions": { "$is": "bar" } },
                "metadata.club": { "conditions": { "$is": "Katowice" } }
            }
        }
    )
    await fake_agent.advanceJob(jobContext)

    assert_message(
        jobContext,
        expectedPatterns = [
            os.environ.get("VF_CUSTOMER_ID_1"),
        ],
        disallowedPatterns = [
            os.environ.get("VF_CUSTOMER_ID_2"),
            os.environ.get("VF_CUSTOMER_ID_3"),
            os.environ.get("VF_CUSTOMER_ID_4"),
        ]
    )
