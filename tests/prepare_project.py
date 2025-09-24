#!/usr/bin/env python3
import os
import sys
import random
import string
from pathlib import Path
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv, dotenv_values
import requests

import voucherify
from voucherify import ApiClient, Configuration
from voucherify.api.management_api import ManagementApi
from voucherify.models import *

load_dotenv()
env_path = Path(__file__).resolve().parent / ".test.env"

def getenv(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name)
    if value is not None and value != "":
        return value
    return default


def ensure_env(var_names: List[str]) -> None:
    missing = [v for v in var_names if not getenv(v)]
    if missing:
        print(
            "Missing required environment variables: " + ", ".join(missing) +
            "\nSet them and re-run."
        )
        sys.exit(1)


def create_test_project(base_url: str, management_id: str, management_token: str) -> Dict[str, str]:
    mgmt_cfg = Configuration(
        host = base_url,
        api_key = {
            "X-Management-Id": management_id,
            "X-Management-Token": management_token
        }
    )
    mgmt_client = ApiClient(mgmt_cfg)
    mgmt_api = ManagementApi(mgmt_client)

    previous_test_project = dotenv_values(env_path)
    previous_test_project_id = previous_test_project.get("TEST_VOUCHERIFY_PROJECT_ID")

    if previous_test_project_id is not None:
        mgmt_api.delete_project(previous_test_project_id)
        print(f"Deleted previous test project {previous_test_project_id}")

    body = ManagementProjectsCreateRequestBody(
        case_sensitive_codes=True,
        name="MCP - Test Project",
        timezone="Europe/Warsaw",
        currency="USD",
    )
    project = mgmt_api.create_project(body)

    creds = {
        "TEST_VOUCHERIFY_PROJECT_ID": project.id,
        "TEST_VOUCHERIFY_API_BASE_URL": base_url,
        "TEST_VOUCHERIFY_APP_ID": project.server_side_key.app_id,
        "TEST_VOUCHERIFY_APP_TOKEN": project.server_side_key.app_token,
    }

    print("Credentials for new test project:")
    print(creds)

    lines = [f"{key}={value}" for key, value in creds.items()]
    env_path.write_text("\n".join(lines) + "\n\n", encoding="utf-8")
    print(f"Saved credentials into {env_path}")

    return creds


def random_code(prefix: str, n: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return prefix + "-" + "".join(random.choice(alphabet) for _ in range(n))


def append_env(env_path: Path, items: Dict[str, str]) -> None:
    with env_path.open("a", encoding="utf-8") as f:
        for key, value in items.items():
            f.write(f"{key}={value}\n")


def main() -> None:
    # Config (env-driven)
    api_base_url = getenv("VOUCHERIFY_API_BASE_URL", "http://localhost:8000")
    management_id = getenv("VOUCHERIFY_MANAGEMENT_APP_ID")
    management_token = getenv("VOUCHERIFY_MANAGEMENT_APP_TOKEN")

    ensure_env(["VOUCHERIFY_MANAGEMENT_APP_ID", "VOUCHERIFY_MANAGEMENT_APP_TOKEN"]) if not (management_id and management_token) else None

    # 1) Create test project (Management API - HTTP)
    print("Creating test project via Management API ...")
    creds = create_test_project(api_base_url, management_id, management_token)

    cfg = Configuration(
        host = api_base_url,
        api_key = {
            "X-App-Id": creds["TEST_VOUCHERIFY_APP_ID"],
            "X-App-Token": creds["TEST_VOUCHERIFY_APP_TOKEN"]
        }
    )
    api_client = ApiClient(cfg)
    customers_api = voucherify.CustomersApi(api_client)
    campaigns_api = voucherify.CampaignsApi(api_client)
    vouchers_api = voucherify.VouchersApi(api_client)
    redemptions_api = voucherify.RedemptionsApi(api_client)
    products_api = voucherify.ProductsApi(api_client)
    loyalties_api = voucherify.LoyaltiesApi(api_client)
    publications_api = voucherify.PublicationsApi(api_client)
    segments_api = voucherify.SegmentsApi(api_client)
    validation_rules_api = voucherify.ValidationRulesApi(api_client)
    promotions_api = voucherify.PromotionsApi(api_client)
    product_collections_api = voucherify.ProductCollectionsApi(api_client)

    # 3) Customers
    print("Creating customers ...")
    customers: List[Dict[str, Any]] = [
        {"source_id": "test-1", "email": "test1@voucherify.io", "metadata": {"foo": "bar", "club": "Katowice"}},
        {"source_id": "test2@voucherify.io", "email": "test2+foobar@voucherify.io", "metadata": {"club": "VIP-Warsaw"}},
        {"source_id": "test-3", "email": "test3@voucherify.io", "metadata": {"club": "VIP-Warsaw"}},
        {"source_id": "test-4", "email": "test4@voucherify.io", "metadata": {"foo": "baz"}},
    ]

    created_customers: Dict[str, CustomersCreateResponseBody] = {}
    for cust in customers:
        created = customers_api.create_customer(CustomersCreateRequestBody(**cust))
        created_customers[created.source_id] = created

    append_env(env_path, {
        "VF_CUSTOMER_ID_1": created_customers["test-1"].id,
        "VF_CUSTOMER_ID_2": created_customers["test2@voucherify.io"].id,
        "VF_CUSTOMER_ID_3": created_customers["test-3"].id,
        "VF_CUSTOMER_ID_4": created_customers["test-4"].id,
    })

    # 3.1) Create segments: VIPs and non-VIPs based on metadata.club
    print("Creating segments VIPs and non-VIPs ...")
    vips_segment = segments_api.create_segment(
        SegmentsCreateRequestBody(
            name = "VIPs",
            type = "auto-update",
            filter = {
                "junction": "and",
                "metadata.club": {
                    "conditions": { "$is": "VIP-Warsaw" }
                }
            }
        )
    )
    non_vips_segment = segments_api.create_segment(
        SegmentsCreateRequestBody(
            name = "non-VIPs",
            type = "auto-update",
            filter = {
                "junction": "and",
                "metadata.club": {
                    "conditions": { "$is_not": "VIP-Warsaw" }
                }
            }
        )
    )
    append_env(env_path, {
        "VF_SEGMENT_VIPS_ID": getattr(vips_segment, "id", "") or "",
        "VF_SEGMENT_NONVIPS_ID": getattr(non_vips_segment, "id", "") or "",
    })

    # 4) Products (Burgers)
    print("Creating products (Burgers) ...")
    burgers: List[Dict[str, Any]] = [
        {"name": "Burger Classic", "price": 1500, "metadata": {"category": "Burgers"}},
        {"name": "Burger Premium", "price": 2100, "metadata": {"category": "Burgers"}},
        {"name":"Burger Deluxe",   "price": 2500, "metadata": {"category": "Burgers"}},
        {"name":"Cesar Salad",     "price": 500, "metadata": {"category": "Salads"}},
        {"name":"Wagyu Steak",     "price": 10000, "metadata": {"category": "Steaks"}},
    ]

    # prepare collection
    print("Creating product collections...")
    # FIXME not using model since it has a bug and doesn't accept AUTO_UPDATE type
    pc_payload = {
        "name": "Meat Dishes",
        "type": "AUTO_UPDATE",
        "filter": {
            "junction": "and",
            "metadata.category": { "conditions": {"$is": [ "Meat" ] } }
        }
    }
    # Call API directly due to SDK limitation for AUTO_UPDATE collections
    resp = requests.post(
        f"{api_base_url}/v1/product-collections",
        headers = {
            "X-App-Id": creds["TEST_VOUCHERIFY_APP_ID"],
            "X-App-Token": creds["TEST_VOUCHERIFY_APP_TOKEN"],
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json = pc_payload,
        timeout = 30,
    )
    resp.raise_for_status()
    meat_collection = ProductCollectionsCreateResponseBody.from_dict(resp.json())
    append_env(env_path, {
        "VF_PRODUCTS_COLLECTION_MEAT_ID": getattr(meat_collection, "id", "") or "",
    })

    created_burgers_ids: List[str] = []
    for burger in burgers:
        p = products_api.create_product(ProductsCreateRequestBody(**burger))
        created_burgers_ids.append(p.id)

    append_env(env_path, {
        "VF_PRODUCT_BURGER_ID_1": created_burgers_ids[0],
        "VF_PRODUCT_BURGER_ID_2": created_burgers_ids[1],
        "VF_PRODUCT_BURGER_ID_3": created_burgers_ids[2],
    })

    # 4.1) Upsell Validation rules
    print("Creating validation rule 'Burger Deluxe for Big Family'")
    burger_deluxe_id = created_burgers_ids[2]
    burger_deluxe_rule = validation_rules_api.create_validation_rules(
        ValidationRulesCreateRequestBody(
            name = "Burger Deluxe for Big Family",
            context_type = "global",
            rules = {
                "1": {
                    "name": "order.items.any",
                    "conditions": {
                        "$is": [
                            {
                                "id": burger_deluxe_id,
                                "type": "product_or_sku",
                                "object": "product",
                                "source_id": None,
                            }
                        ]
                    },
                    "rules": {
                        "1": {
                            "name": "order.items.aggregated_quantity",
                            "conditions": { "$more_than_or_equal": [4] },
                            "rules": {},
                        },
                        "logic": "1",
                    },
                },
                "logic": "1",
            },
            applicable_to = ValidationRulesCreateRequestBodyApplicableTo(
                excluded = [],
                included = [
                    ApplicableTo(
                        object = "product",
                        id = burger_deluxe_id,
                        strict = False,
                        effect = ApplicableToEffect.APPLY_TO_EVERY,
                        skip_initially = 0,
                        repeat = 1,
                        target = "ITEM",
                    )
                ],
                included_all = False,
            ),
        )
    )

    meat_collection_rule = validation_rules_api.create_validation_rules(
        ValidationRulesCreateRequestBody(
            name = "Meat Dishes 2$ discount per item for 3 or more items",
            context_type = "global",
            rules = {
                "1": {
                    "name": "order.items.any",
                    "conditions": {
                        "$is": [
                            {
                                "id": meat_collection.id,
                                "type": "products_collection",
                                "object": "products_collection"
                            }
                        ]
                    },
                    "rules": {
                        "1": {
                            "name": "order.items.aggregated_quantity",
                            "conditions": { "$more_than_or_equal": [3] },
                            "rules": {},
                        },
                        "logic": "1",
                    },
                },
                "logic": "1",
            },
            applicable_to = ValidationRulesCreateRequestBodyApplicableTo(
                excluded = [],
                included = [
                    ApplicableTo(
                        object = "products_collection",
                        id = meat_collection.id,
                        strict = False,
                        effect = ApplicableToEffect.APPLY_TO_EVERY,
                        skip_initially = 0,
                        repeat = 1,
                        target = "ITEM",
                    )
                ],
                included_all = False,
            ),
        )
    )

    append_env(env_path, {
        "VF_VAL_RULE_BURGER_DELUXE_ID": burger_deluxe_rule.id,
    })


    # 8.1) Create validation rules for segments and add two more promotion tiers
    print("Creating validation rules for segments and adding promotion tiers ...")

    # Validation rule: customer is in VIPs segment
    vips_rule = validation_rules_api.create_validation_rules(
        ValidationRulesCreateRequestBody(
            name = "Customer in VIPs",
            context_type = "campaign.promotion",
            rules = {
                "1": {
                    "name": "customer.segment",
                    "conditions": { "$is": [vips_segment.id] }
                },
                "logic": "1"
            }
        )
    )

    # Validation rule: customer is in non-VIPs segment
    non_vips_rule = validation_rules_api.create_validation_rules(
        ValidationRulesCreateRequestBody(
            name = "Customer in non-VIPs",
            context_type = "campaign.promotion",
            rules = {
                "1": {
                    "name": "customer.segment",
                    "conditions": { "$is": [non_vips_segment.id] }
                },
                "logic": "1"
            }
        )
    )

    append_env(env_path, {
        "VF_VAL_RULE_VIPS_ID": vips_rule.id,
        "VF_VAL_RULE_NONVIPS_ID": non_vips_rule.id,
    })

    # 5) Discount campaign with defined budget (generate few vouchers)
    print("Creating discount campaign 'BK-Sept-20OFF' ...")
    campaign_payload = CampaignsCreateRequestBody(
        campaign_type="DISCOUNT_COUPONS",
        name="BK-Sept-20OFF",
        voucher=CampaignsCreateRequestBodyVoucher(
            type="DISCOUNT_VOUCHER",
            discount=Discount(type="PERCENT", percent_off=20)
        ),
    )
    campaign = campaigns_api.create_campaign(campaign_payload)
    campaign_id = campaign.id
    append_env(env_path, {
        "VF_CAMPAIGN_ID_BK_SEPT_20OFF": campaign_id,
    })

    # Define budget by creating a handful of vouchers assigned to the campaign
    print("Generating vouchers for campaign budget ...")
    generated_codes: List[str] = []
    for _ in range(5):  # generate 5 vouchers as the campaign budget
        code = random_code("BKSEPT20")
        voucher_payload = VouchersCreateWithSpecificCodeRequestBody(
            type="DISCOUNT_VOUCHER",
            discount=Discount(type="PERCENT", percent_off=20),
            campaign_id=campaign_id,
        )
        v = vouchers_api.create_voucher(code, voucher_payload)
        generated_codes.append(v.code or code)

    # 6) Redeem a few coupons for existing customers
    print("Redeeming a few vouchers ...")
    redeem_pairs = list(zip(generated_codes[:3], [c["source_id"] for c in customers[:3]]))
    for code, source_id in redeem_pairs:
        redemption_payload = RedemptionsRedeemRequestBody(
            customer=Customer(source_id=source_id),
            redeemables=[RedemptionsRedeemRequestBodyRedeemablesItem(object="voucher", id=code)],
        )
        redemptions_api.redeem_stacked_discounts(redemption_payload)

    # 7) Another inactive campaign
    print("Creating another inactive campaign ...")
    inactive_campaign_payload = CampaignsCreateRequestBody(
        name="BK-Inactive",
        campaign_type="DISCOUNT_COUPONS",
        voucher=CampaignsCreateRequestBodyVoucher(
            type="DISCOUNT_VOUCHER",
            discount=Discount(type="PERCENT", percent_off=15)
        ),
    )
    campaigns_api.create_campaign(inactive_campaign_payload)

    # 8) Promotion campaign with example tier
    print("Creating promotion campaign with a tier ...")
    promotion_campaign_payload = CampaignsCreateRequestBody(
        campaign_type="PROMOTION",
        name="Promotion - Example",
        promotion=CampaignsCreateRequestBodyPromotion(
            tiers=[
                PromotionTierCreateParams(
                    name="Percent Discount",
                    banner="All Gets 5% off",
                    action=PromotionTierCreateParamsAction(
                        discount=Discount(type="PERCENT", percent_off=5, effect="APPLY_TO_ORDER")
                    )
                ),
                PromotionTierCreateParams(
                    name = "VIPs 40% off",
                    banner = "VIPs get 40% off",
                    action = PromotionTierCreateParamsAction(
                        discount = Discount(type = "PERCENT", percent_off = 40, effect = "APPLY_TO_ORDER")
                    ),
                    validation_rules = [vips_rule.id]
                ),
                PromotionTierCreateParams(
                    name = "non-VIPs 10% off",
                    banner = "non-VIPs get 10% off",
                    action = PromotionTierCreateParamsAction(
                        discount = Discount(type = "PERCENT", percent_off = 10, effect = "APPLY_TO_ORDER")
                    ),
                    validation_rules = [non_vips_rule.id]
                ),
                # Upsell promotion tiers
                PromotionTierCreateParams(
                    name = "Burger Deluxe for Big Family",
                    banner = "Burger Deluxe for Big Family 15% off",
                    action = PromotionTierCreateParamsAction(
                        discount = Discount(type = "PERCENT", percent_off = 15, effect = "APPLY_TO_ITEMS")
                    ),
                    validation_rules = [burger_deluxe_rule.id]
                ),
                PromotionTierCreateParams(
                    name = "Meat Dishes 2$ discount per item",
                    banner = "2$ discount per meat dish",
                    action = PromotionTierCreateParamsAction(
                        discount = Discount(type = "AMOUNT", amount_off = 200, effect = "APPLY_TO_ITEMS_BY_QUANTITY")
                    ),
                    validation_rules = [meat_collection_rule.id]
                ),
            ]
        ),
    )
    promo_campaign = campaigns_api.create_campaign(promotion_campaign_payload)

    append_env(env_path, {
        "VF_PROMO_CAMPAIGN_ID": promo_campaign.id,
        "VF_PROMO_TIER_ID": promo_campaign.promotion.tiers[0].id,
        "VF_PROMO_TIER_VIPS_ID": promo_campaign.promotion.tiers[1].id,
        "VF_PROMO_TIER_NONVIPS_ID": promo_campaign.promotion.tiers[2].id,
        "VF_PROMO_TIER_BURGER_DELUXE_ID": promo_campaign.promotion.tiers[3].id,
        "VF_PROMO_TIER_MEAT_DISHES_ID": promo_campaign.promotion.tiers[4].id,
    })

    # 9) Loyalty program + loyalty card for customer 1 with 140 points
    print("Creating loyalty campaign and assigning loyalty card to customer 1 ...")
    loyalty_campaign_name = f"Test loyalty program: {random_code('LP')[3:]}"
    loyalty_campaign = loyalties_api.create_loyalty_program(
        voucherify.LoyaltiesCreateCampaignRequestBody(
            name = loyalty_campaign_name,
            campaign_type = "LOYALTY_PROGRAM",
            type = "AUTO_UPDATE",
            auto_join = True,
            join_once = True,
            voucher = voucherify.CampaignLoyaltyVoucher(
                type = "LOYALTY_CARD",
                loyalty_card = voucherify.CampaignLoyaltyCard(points=0)
            )
        )
    )
    loyalty_campaign_id = loyalty_campaign.id
    append_env(env_path, {
        "VF_LOYALTY_CAMPAIGN_ID": loyalty_campaign_id,
    })

    # Create loyalty card voucher with 140 points and publish to customer 1
    loyalty_card_code = random_code("LOYALTY")
    loyalty_card_voucher = vouchers_api.create_voucher(
        loyalty_card_code,
        voucherify.VouchersCreateWithSpecificCodeRequestBody(
            type = "LOYALTY_CARD",
            campaign_id = loyalty_campaign_id,
            loyalty_card = voucherify.SimpleLoyaltyCard(points=140)
        )
    )

    # Publish loyalty card to customer 1
    cust1_id = created_customers["test-1"].id
    publications_api.create_publication(
        publications_create_request_body = voucherify.PublicationsCreateRequestBody(
            customer = voucherify.Customer(id=cust1_id),
            voucher = loyalty_card_code,
        )
    )
    append_env(env_path, {
        "VF_LOYALTY_CARD_CODE_1": loyalty_card_code,
        "VF_LOYALTY_CARD_ID_1": getattr(loyalty_card_voucher, "id", "") or "",
    })

    # 10) Create three discount vouchers; publish two to customer 1
    print("Creating and publishing two discount vouchers to customer 1; one unassigned ...")
    code1 = random_code("CUST1")
    code2 = random_code("CUST1")
    code_free = random_code("FREE1")

    def create_discount_voucher(code: str):
        payload = VouchersCreateWithSpecificCodeRequestBody(
            type="DISCOUNT_VOUCHER",
            discount=Discount(type="PERCENT", percent_off=10),
        )
        return vouchers_api.create_voucher(code, payload)

    v1 = create_discount_voucher(code1)
    v2 = create_discount_voucher(code2)
    vfree = create_discount_voucher(code_free)

    # Publish two vouchers to customer 1
    for code in [code1, code2]:
        publications_api.create_publication(
            publications_create_request_body = voucherify.PublicationsCreateRequestBody(
                customer = voucherify.Customer(id=cust1_id),
                voucher = code,
            )
        )

    append_env(env_path, {
        "VF_VOUCHER_CUST_1_1": code1,
        "VF_VOUCHER_CUST_1_2": code2,
        "VF_VOUCHER_FREE_1": code_free,
        "VF_VOUCHER_CUST_1_1_ID": getattr(v1, "id", "") or "",
        "VF_VOUCHER_CUST_1_2_ID": getattr(v2, "id", "") or "",
        "VF_VOUCHER_FREE_1_ID": getattr(vfree, "id", "") or "",
        "VF_VOUCHER_CUST_1_1_CODE": code1,
        "VF_VOUCHER_CUST_1_2_CODE": code2,
        "VF_VOUCHER_FREE_1_CODE": code_free,
    })

    # 11) Create standalone discount voucher with burger_deluxe_rule validation and publish to customer 1
    print("Creating standalone discount voucher with burger_deluxe_rule validation and publishing to customer 1 ...")
    burger_deluxe_code = random_code("DELUXE")
    burger_deluxe_voucher = vouchers_api.create_voucher(
        burger_deluxe_code,
        VouchersCreateWithSpecificCodeRequestBody(
            type = "DISCOUNT_VOUCHER",
            discount = Discount(type = "PERCENT", percent_off = 25),
            validation_rules = [burger_deluxe_rule.id],
            validity_day_of_week = [1, 2, 3, 4, 5]  # Monday to Friday (working days)
        )
    )

    # Publish burger deluxe voucher to customer 1
    publications_api.create_publication(
        publications_create_request_body = voucherify.PublicationsCreateRequestBody(
            customer = voucherify.Customer(id = cust1_id),
            voucher = burger_deluxe_code,
        )
    )

    append_env(env_path, {
        "VF_VOUCHER_BURGER_DELUXE_CODE": burger_deluxe_code,
        "VF_VOUCHER_BURGER_DELUXE_ID": burger_deluxe_voucher.id,
    })

    # 12) Create discount campaign with 10 vouchers and burger_deluxe_rule validation
    print("Creating discount campaign with 10 vouchers and burger_deluxe_rule validation ...")
    burger_campaign_payload = CampaignsCreateRequestBody(
        campaign_type = "DISCOUNT_COUPONS",
        name = "Burger Deluxe Family Campaign",
        voucher = CampaignsCreateRequestBodyVoucher(
            type = "DISCOUNT_VOUCHER",
            discount = Discount(type = "PERCENT", percent_off = 3),
            validity_day_of_week = [1, 2, 3, 4, 5]  # Monday to Friday (working days)
        ),
        validation_rules = [burger_deluxe_rule.id],
        vouchers_count = 10
    )
    burger_campaign = campaigns_api.create_campaign(burger_campaign_payload)

    append_env(env_path, {
        "VF_BURGER_DELUXE_CAMPAIGN_ID": burger_campaign.id,
    })

    print("All done.")


if __name__ == "__main__":
    main()


