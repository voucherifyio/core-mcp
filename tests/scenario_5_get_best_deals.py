import os
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
async def test_get_best_deals(fake_agent: FakeAgent):
    # job_goal = "Get summary for campaign BK Sept 20OFF"
    productId = os.environ.get("VF_PRODUCT_BURGER_ID_3")
    job_goal = f"Find best deal for customer with email test1@voucherify.io which has in the backet one quantity of product with id {productId} and 2 quantities of product with metadata 'category' set to 'Meat'. Include in response redeemable ids."
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
        expectedToolName = "get_best_deals",
        expectedToolArgs = {
            "customer": {
                "id": os.environ.get("VF_CUSTOMER_ID_1")
            },
            "order": {
                "items": [
                    { "product_id": productId, "quantity": 1 },
                    { "quantity": 2, "product": { "metadata": { "category": "Meat" } } }
                ]
            }
        }
    )

    await fake_agent.advanceJob(jobContext)

    assert_message(
        jobContext,
        expectedPatterns = [
            os.environ.get("VF_PROMO_TIER_BURGER_DELUXE_ID"),
            os.environ.get("VF_PROMO_TIER_MEAT_DISHES_ID")
        ]
    )


@pytest.mark.asyncio
async def test_get_best_deals_json_output(fake_agent: FakeAgent):
    # job_goal = "Get summary for campaign BK Sept 20OFF"
    productId = os.environ.get("VF_PRODUCT_BURGER_ID_3")
    job_goal = f"""
    Find best deal for customer with email test1@voucherify.io which has in the bucket one quantity of product with id {productId} for 15.50$ and 2 quantities of product with metadata 'category' set to 'Meat' for 10$ each. Return result in json format consistent with example below.
    """ + """
    Example output:
    {
        "best_deals": [
            {
                "name": "descriptive name",
                "description": "short description to display",
                "redeemable": { "type": "promotion", "id": "promo_123", "banner": "banner text" },
                "required_additional_items_to_qualify": [
                    { "product_id": "prod_123", "name": "Ice Cream", "additional_quantity": 1 },
                ],
                "savings_for_the_user": "short description of the savings"
            }
        ]
    }
    """

    # Step 1
    jobContext = await fake_agent.startJob(job_goal)
    assert_tool_call(
        jobContext,
        expectedToolName = "find_customer",
        expectedToolArgs = {
            "email": "test1@voucherify.io",
            "id": None
        }
    )

    # Step 2
    await fake_agent.advanceJob(jobContext)
    assert_tool_call(
        jobContext,
        expectedToolName = "get_best_deals",
        expectedToolArgs = {
            "customer": {
                "id": os.environ.get("VF_CUSTOMER_ID_1")
            },
            "order": {
                "items": [
                    { "product_id": productId, "quantity": 1, "price": 1550 },
                    { "quantity": 2, "product": { "metadata": { "category": "Meat" } }, "price": 1000 }
                ]
            }
        }
    )

    # Step 3
    await fake_agent.advanceJob(jobContext)
    assert_message(
        jobContext,
        expectedPatterns = [
            os.environ.get("VF_PROMO_TIER_BURGER_DELUXE_ID"),
            os.environ.get("VF_PROMO_TIER_MEAT_DISHES_ID")
        ]
    )