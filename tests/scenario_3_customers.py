import os
import re
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
async def test_find_customer_by_email_and_wallet(fake_agent: FakeAgent):
    job_goal = "Find customer by email test1@voucherify.io and return id, loyalty balance and active vouchers."
    jobContext = await fake_agent.startJob(job_goal)

    assert_tool_call(
        jobContext,
        expectedToolName = "find_customer",
        expectedToolArgs = {
            "email": "test1@voucherify.io",
            "id": None
        }
    )
    await fake_agent.advanceJob(jobContext)

    assert_tool_call(
        jobContext,
        expectedToolName = "qualifications",
        expectedToolArgs = {
            "customer": { "id": os.environ.get("VF_CUSTOMER_ID_1") },
            "scenario": "CUSTOMER_WALLET"
        }
    )
    await fake_agent.advanceJob(jobContext)

    # Final message should include id and balance/vouchers specifics
    assert_message(
        jobContext,
        expectedPatterns = [
            os.environ.get("VF_CUSTOMER_ID_1"),
            "140 points",
            os.environ.get("VF_VOUCHER_CUST_1_1_CODE"),
            os.environ.get("VF_VOUCHER_CUST_1_2_CODE"),

        ],
        disallowedPatterns = [
            os.environ.get("VF_VOUCHER_FREE_1_CODE"),
        ]
    )

@pytest.mark.asyncio
async def test_find_customer_promotions(fake_agent: FakeAgent):
    job_goal = "Find customer by email test3@voucherify.io and return id, loyalty balance and available promotions (just ids and discount details) for him."
    jobContext = await fake_agent.startJob(job_goal)

    assert_tool_call(
        jobContext,
        expectedToolName = "find_customer",
        expectedToolArgs = {
            "email": "test3@voucherify.io",
            "id": None
        }
    )
    await fake_agent.advanceJob(jobContext)

    assert_tool_call(
        jobContext,
        expectedToolName = "qualifications",
        expectedToolArgs = {
            "customer": { "id": os.environ.get("VF_CUSTOMER_ID_3") },
            "scenario": "AUDIENCE_ONLY"
        }
    )
    await fake_agent.advanceJob(jobContext)

    # Final message should include id and balance/vouchers specifics
    assert_message(
        jobContext,
        expectedPatterns = [
            os.environ.get("VF_CUSTOMER_ID_3"),
            os.environ.get("VF_PROMO_TIER_ID"),
            os.environ.get("VF_PROMO_TIER_VIPS_ID"),

        ],
        disallowedPatterns = [
            os.environ.get("VF_PROMO_TIER_NONVIPS_ID")
        ]
    )

@pytest.mark.asyncio
async def test_find_customer_promotions_and_vouchers(fake_agent: FakeAgent):
    job_goal = "Find customer by email test1@voucherify.io and return id, loyalty balance and available promotions and active vouchers."
    jobContext = await fake_agent.startJob(job_goal)

    # Step 1: find customer
    assert_tool_call(
        jobContext,
        expectedToolName = "find_customer",
        expectedToolArgs = {
            "email": "test1@voucherify.io",
            "id": None
        }
    )
    await fake_agent.advanceJob(jobContext)

    # Step 2: use qualifications tool twice

    assert_tool_call(
        jobContext,
        expectedToolName = "qualifications",
        expectedToolArgs = {
            "customer": { "id": os.environ.get("VF_CUSTOMER_ID_1") },
            "scenario": "AUDIENCE_ONLY"
        }
    )
    assert_tool_call(
        jobContext,
        expectedToolName = "qualifications",
        expectedToolArgs = {
            "customer": { "id": os.environ.get("VF_CUSTOMER_ID_1") },
            "scenario": "CUSTOMER_WALLET"
        }
    )
    assert_tool_call_count(jobContext, 2)
    await fake_agent.advanceJob(jobContext)

    # Final message should include id and balance/vouchers specifics
    assert_message(
        jobContext,
        expectedPatterns = [
            os.environ.get("VF_CUSTOMER_ID_1"),
            "140",
            os.environ.get("VF_VOUCHER_CUST_1_1_CODE"),
            os.environ.get("VF_VOUCHER_CUST_1_2_CODE"),
            os.environ.get("VF_PROMO_TIER_NONVIPS_ID"),

        ],
        disallowedPatterns = [
            os.environ.get("VF_VOUCHER_FREE_1_CODE"),
            os.environ.get("VF_PROMO_TIER_VIPS_ID"),
        ]
    )
