import os
import pytest
import pytest_asyncio
import logging
from .test_utils import FakeAgent, assert_tool_call, assert_message

logger = logging.getLogger(__name__)

model = "gpt-5.2"  # OpenAI


@pytest_asyncio.fixture(scope="session")
async def fake_agent():
    agent = FakeAgent(
        apiBaseUrl=os.environ.get("TEST_VOUCHERIFY_API_BASE_URL"),
        appId=os.environ.get("TEST_VOUCHERIFY_APP_ID"),
        appToken=os.environ.get("TEST_VOUCHERIFY_APP_TOKEN"),
        model=model,
        serverPath="src/voucherify_core_mcp/main.py",
    )
    await agent.initialize()
    return agent


MAX_RETRIES = 3


def _args_match(actual: dict, expected: dict) -> bool:
    """Check that actual args contain all expected non-None key-value pairs."""
    for key, value in expected.items():
        if value is None:
            continue
        if key not in actual or actual[key] != value:
            return False
    return True


async def advance_until_tool_call(fake_agent, jobContext, expected_tool_name, expected_tool_args):
    """Advance the job up to MAX_RETRIES times until the model sends the expected tool call."""
    for attempt in range(MAX_RETRIES):
        await fake_agent.advanceJob(jobContext)
        last = jobContext.getLastStepModelResponses()
        tool_calls = [r for r in last if r["type"] == "tool_call"]
        for tc in tool_calls:
            if tc["name"] == expected_tool_name and _args_match(tc["arguments"], expected_tool_args):
                return
        logger.info(
            "Attempt %d: model sent %s, expected %s — letting it self-correct",
            attempt + 1,
            [tc["arguments"] for tc in tool_calls],
            expected_tool_args,
        )
    pytest.fail(
        f"(Step: {jobContext.step}) Model did not send expected tool call "
        f"'{expected_tool_name}' with args {expected_tool_args} after {MAX_RETRIES} retries"
    )


@pytest.mark.asyncio
async def test_estimate_loyalty_points_by_card(fake_agent: FakeAgent):
    loyalty_card_code = os.environ.get("VF_LOYALTY_CARD_CODE_1")
    job_goal = (
        f"Estimate how many loyalty points customer with email test1@voucherify.io "
        f"will earn for an order worth $50. "
        f"Use their loyalty card code {loyalty_card_code}. "
        f"Include the points estimation in the response."
    )

    # Step 1: LLM should resolve the customer first
    jobContext = await fake_agent.startJob(job_goal)
    assert_tool_call(
        jobContext,
        expectedToolName="find_customer",
        expectedToolArgs={"email": "test1@voucherify.io", "id": None},
    )

    # Step 2+: LLM should call estimate_loyalty_points with all required params
    # May take a retry if the model initially omits customer/order
    await advance_until_tool_call(
        fake_agent,
        jobContext,
        expected_tool_name="estimate_loyalty_points",
        expected_tool_args={
            "loyalty_card": loyalty_card_code,
            "customer": {"id": os.environ.get("VF_CUSTOMER_ID_1")},
            "order": {"amount": 5000},
        },
    )

    # Final step: Response should mention points estimation
    await fake_agent.advanceJob(jobContext)
    assert_message(
        jobContext,
        expectedPatterns=["points"],
    )


@pytest.mark.asyncio
async def test_estimate_loyalty_points_by_campaign_id(fake_agent: FakeAgent):
    loyalty_campaign_id = os.environ.get("VF_LOYALTY_CAMPAIGN_ID")
    customer_id = os.environ.get("VF_CUSTOMER_ID_1")
    job_goal = (
        f"Estimate how many loyalty points customer {customer_id} "
        f"will earn in loyalty campaign {loyalty_campaign_id} "
        f"for an order of $30. Include the points estimation in the response."
    )

    # Step 1+: LLM should call estimate_loyalty_points directly with campaign_id
    jobContext = await fake_agent.startJob(job_goal)
    last = jobContext.getLastStepModelResponses()
    expected_args = {
        "campaign_id": loyalty_campaign_id,
        "customer": {"id": customer_id},
        "order": {"amount": 3000},
    }
    tool_calls = [r for r in last if r["type"] == "tool_call"]
    first_correct = any(
        tc["name"] == "estimate_loyalty_points"
        and _args_match(tc["arguments"], expected_args)
        for tc in tool_calls
    )
    if not first_correct:
        await advance_until_tool_call(
            fake_agent,
            jobContext,
            expected_tool_name="estimate_loyalty_points",
            expected_tool_args=expected_args,
        )

    # Final step: Response should mention points estimation
    await fake_agent.advanceJob(jobContext)
    assert_message(
        jobContext,
        expectedPatterns=["points"],
    )