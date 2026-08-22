from app.security.pii_masking import mask_sensitive_result


def test_masks_only_the_configured_sensitive_columns() -> None:
    result = mask_sensitive_result({
        "CardNumber": "4111111111111111",
        "ExpMonth": 12,
        "ExpYear": 2028,
        "CreditCardApprovalCode": "ABC123XYZ",
        "AccountNumber": "AW00000001",
        "PurchaseOrderNumber": "PO12345",
        "TotalDue": 120.5,
    })

    assert result == {
        "CardNumber": "************1111",
        "ExpMonth": "**",
        "ExpYear": "****",
        "CreditCardApprovalCode": "*********",
        "AccountNumber": "AW00000001",
        "PurchaseOrderNumber": "PO12345",
        "TotalDue": 120.5,
    }


def test_masks_sensitive_fields_in_nested_result_shapes() -> None:
    result = mask_sensitive_result({
        "customer": {"CardNumber": "5555555555554444"},
        "orders": [{"CreditCardApprovalCode": "XYZ"}],
    })

    assert result == {
        "customer": {"CardNumber": "************4444"},
        "orders": [{"CreditCardApprovalCode": "***"}],
    }
