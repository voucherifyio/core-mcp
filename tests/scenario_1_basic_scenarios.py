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


# Vouchers

@pytest.mark.asyncio
async def test_get_voucher(fake_agent: FakeAgent):
    job_goal = f"Show me details about promo code {os.environ.get('VF_VOUCHER_BURGER_DELUXE_CODE')}"
    jobContext = await fake_agent.startJob(job_goal)

    assert_tool_call(
        jobContext,
        expectedToolName = "get_voucher",
        expectedToolArgs = {
            "identifier": os.environ.get("VF_VOUCHER_BURGER_DELUXE_CODE")
        }
    )
    await fake_agent.advanceJob(jobContext)

    assert_message(
        jobContext,
        expectedPatterns = [
            os.environ.get("VF_VOUCHER_BURGER_DELUXE_CODE"),
            os.environ.get("VF_CUSTOMER_ID_1"),
        ]
    )

@pytest.mark.asyncio
async def test_get_voucher_without_validation_rules(fake_agent: FakeAgent):
    job_goal = f"Show me details about promo code {os.environ.get('VF_VOUCHER_FREE_1_CODE')}"
    jobContext = await fake_agent.startJob(job_goal)

    assert_tool_call(
        jobContext,
        expectedToolName = "get_voucher",
        expectedToolArgs = { "identifier": os.environ.get("VF_VOUCHER_FREE_1_CODE") }
    )
    await fake_agent.advanceJob(jobContext)

    assert_message(
        jobContext,
        expectedPatterns = [ os.environ.get("VF_VOUCHER_FREE_1_CODE") ]
    )

# Campaigns

@pytest.mark.asyncio
async def test_get_campaign(fake_agent: FakeAgent):
    job_goal = f"Show me details about campaign {os.environ.get('VF_BURGER_DELUXE_CAMPAIGN_ID')}"
    jobContext = await fake_agent.startJob(job_goal)
    assert_tool_call(
        jobContext,
        expectedToolName = "get_campaign",
        expectedToolArgs = { "campaign_id": os.environ.get("VF_BURGER_DELUXE_CAMPAIGN_ID") }
    )
    await fake_agent.advanceJob(jobContext)
    assert_message(
        jobContext,
        expectedPatterns = [ os.environ.get("VF_BURGER_DELUXE_CAMPAIGN_ID") ]
    )

# Promotion tiers

@pytest.mark.asyncio
async def test_get_promotion_tier(fake_agent: FakeAgent):
    job_goal = f"Show me details about promotion {os.environ.get('VF_PROMO_TIER_MEAT_DISHES_ID')}"
    jobContext = await fake_agent.startJob(job_goal)
    assert_tool_call(
        jobContext,
        expectedToolName = "get_promotion_tier",
        expectedToolArgs = { "promotion_tier_id": os.environ.get("VF_PROMO_TIER_MEAT_DISHES_ID") }
    )
    await fake_agent.advanceJob(jobContext)
    assert_message(
        jobContext,
        expectedPatterns = [ os.environ.get("VF_PROMO_TIER_MEAT_DISHES_ID") ]
    )