import os
import re
from datetime import datetime, timedelta, date
import calendar
import pytest
import pytest_asyncio
import logging
from .test_utils import FakeAgent, assert_tool_call, assert_message, assert_tool_call_count

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
async def test_camp_summary(fake_agent: FakeAgent):
    # job_goal = "Get summary for campaign BK Sept 20OFF"
    job_goal = "Get summary for campaign BK Sept 20OFF for last month and compare it with this month"
    jobContext = await fake_agent.startJob(job_goal)

    assert_tool_call(
        jobContext,
        expectedToolName = "list_campaigns",
        expectedToolArgs = {}
    )
    await fake_agent.advanceJob(jobContext)

    today = date.today()
    this_month_start = today.replace(day=1)
    this_month_end = today
    last_month_end = this_month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    assert_tool_call(
        jobContext,
        expectedToolName = "get_campaign_summary",
        expectedToolArgs = {
            "campaign_id": os.environ.get("VF_CAMPAIGN_ID_BK_SEPT_20OFF"),
            "start_date": last_month_start.strftime("%Y-%m-%d"),
            "end_date": last_month_end.strftime("%Y-%m-%d")
        }
    )
    assert_tool_call(
        jobContext,
        expectedToolName = "get_campaign_summary",
        expectedToolArgs = {
            "campaign_id": os.environ.get("VF_CAMPAIGN_ID_BK_SEPT_20OFF"),
            "start_date": this_month_start.strftime("%Y-%m-%d"),
            "end_date": this_month_end.strftime("%Y-%m-%d")
        }
    )
    assert_tool_call_count(jobContext, 2)

    await fake_agent.advanceJob(jobContext)

    # Final message should include id and balance/vouchers specifics
    assert_message(
        jobContext,
        expectedPatterns = [
            # os.environ.get("VF_CUSTOMER_ID_1"),
            # "140 points",
            # os.environ.get("VF_VOUCHER_CUST_1_1_CODE"),
            # os.environ.get("VF_VOUCHER_CUST_1_2_CODE"),

        ],
        disallowedPatterns = [
            # os.environ.get("VF_VOUCHER_FREE_1_CODE"),
        ]
    )
