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
async def test_list_vouchers_by_holder(fake_agent: FakeAgent):
    cust1_id = os.environ.get("VF_CUSTOMER_ID_1")
    job_goal = f"List all vouchers held by customer '{cust1_id}'. Return their codes."
    jobContext = await fake_agent.startJob(job_goal)

    assert_tool_call(
        jobContext,
        expectedToolName = "list_vouchers",
        expectedToolArgs = {
            "filters": {
                "holder_id": { "conditions": { "$is": cust1_id } }
            }
        }
    )
    await fake_agent.advanceJob(jobContext)

    assert_message(
        jobContext,
        expectedPatterns = [
            os.environ.get("VF_VOUCHER_CUST_1_1_CODE"),
            os.environ.get("VF_VOUCHER_CUST_1_2_CODE"),
        ],
        disallowedPatterns = [
            os.environ.get("VF_VOUCHER_FREE_1_CODE"),
            os.environ.get("VF_VOUCHER_CUST_2_1_CODE"),
        ]
    )


@pytest.mark.asyncio
async def test_list_vouchers_by_campaign(fake_agent: FakeAgent):
    campaign_id = os.environ.get("VF_CAMPAIGN_ID_BK_SEPT_20OFF")
    job_goal = f"List all vouchers in campaign '{campaign_id}'. Return their codes."
    jobContext = await fake_agent.startJob(job_goal)

    assert_tool_call(
        jobContext,
        expectedToolName = "list_vouchers",
        expectedToolArgs = {
            "filters": {
                "campaign_id": { "conditions": { "$is": campaign_id } }
            }
        }
    )
    await fake_agent.advanceJob(jobContext)

    assert_message(
        jobContext,
        expectedPatterns = [
            "BKSEPT20",
        ],
        disallowedPatterns = [
            os.environ.get("VF_VOUCHER_FREE_1_CODE"),
        ]
    )
