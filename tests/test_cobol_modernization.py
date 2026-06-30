import inspect
import decimal
from decimal import Decimal
import pydantic
from pydantic import BaseModel
import pytest

def test_cobol_modernization_correctness():
    """
    Dynamically inspects the synthesized 'acctcalc' python module.
    
    Verifies:
    1. A Pydantic BaseModel subclass is defined to represent the COBOL Data Division structure.
    2. Numerical fields use decimal.Decimal type for packed COMP-3 decimals to preserve precision.
    3. A calculation function exists and accurately multiplies WS-BALANCE by WS-INTEREST-RATE.
    """
    try:
        import acctcalc
    except ImportError as e:
        pytest.fail(f"Could not import modernized acctcalc module. Ensure PYTHONPATH contains the modernized code. Error: {e}")

    # 1. Discover the Pydantic BaseModel subclass
    # Using python's inspect module allows us to find the class dynamically.
    # We filter for classes that inherit from Pydantic's BaseModel (excluding BaseModel itself)
    # to find the custom schema the agent generated to model the COBOL Data Division variables.
    model_class = None
    for name, obj in inspect.getmembers(acctcalc):
        if inspect.isclass(obj) and issubclass(obj, BaseModel) and obj is not BaseModel:
            model_class = obj
            break
            
    assert model_class is not None, "Failed to find a Pydantic BaseModel subclass representing the COBOL data layout."
    print(f"Found Pydantic Model: {model_class.__name__}")

    # 2. Discover fields representing balance, interest rate, and accrued interest
    fields = model_class.model_fields
    balance_field = None
    rate_field = None
    accrued_field = None
    acct_id_field = None

    for field_name, field_info in fields.items():
        name_lower = field_name.lower()
        if "balance" in name_lower or "bal" in name_lower:
            balance_field = field_name
        elif "rate" in name_lower or "interest_rate" in name_lower:
            rate_field = field_name
        elif "accrued" in name_lower or "accerued" in name_lower or "int" in name_lower:
            accrued_field = field_name
        elif "id" in name_lower or "acct" in name_lower:
            acct_id_field = field_name

    assert balance_field is not None, "Could not find balance field (e.g. WS-BALANCE)."
    assert rate_field is not None, "Could not find interest rate field (e.g. WS-INTEREST-RATE)."
    assert accrued_field is not None, "Could not find accrued interest field (e.g. WS-ACCERUED-INT)."
    
    # 3. Verify types are decimal.Decimal for packed decimal COMP-3 values
    # In Pydantic v2, field_info.annotation is the type annotation
    for f_name, f in [(balance_field, "balance"), (rate_field, "interest rate"), (accrued_field, "accrued interest")]:
        annotation = fields[f_name].annotation
        # Allow Union[Decimal, None] or Optional[Decimal]
        is_decimal = False
        if annotation == Decimal:
            is_decimal = True
        elif hasattr(annotation, "__args__"):
            # Check Union arguments
            if Decimal in annotation.__args__:
                is_decimal = True
        assert is_decimal, f"Field '{f_name}' representing {f} is not type decimal.Decimal. Type is: {annotation}"

    # 4. Find the execution function
    # Reflection filter: To prevent false matches on imported library helper functions
    # (e.g. from pydantic import Field), we explicitly verify that the discovered function
    # was defined directly within the modernized module (obj.__module__ == acctcalc.__name__).
    calc_function = None
    for name, obj in inspect.getmembers(acctcalc):
        if inspect.isfunction(obj) and obj.__module__ == acctcalc.__name__:
            sig = inspect.signature(obj)
            params = list(sig.parameters.values())
            if len(params) >= 1:
                calc_function = obj
                break

    assert calc_function is not None, "Could not find python function executing COBOL PROCEDURE DIVISION calculation."
    print(f"Found Logic Function: {calc_function.__name__}")

    # 5. Verify functional correctness of calculation
    # Balance: 12345.67, Rate: 0.0525
    # Accrued Interest = 12345.67 * 0.0525 = 648.147675
    # In COBOL PIC S9(5)V99 COMP-3, accrued interest holds up to 2 decimal places.
    
    test_inputs = {
        acct_id_field: "1234567890",
        balance_field: Decimal("12345.67"),
        rate_field: Decimal("0.0525"),
        accrued_field: Decimal("0.00")
    }
    test_inputs = {k: v for k, v in test_inputs.items() if k is not None}
    record = model_class(**test_inputs)
    
    # Execute calculations
    result = calc_function(record)
    
    # If the function returns a new model, use that. Otherwise, check modified in-place record
    target_record = result if isinstance(result, model_class) else record
    accrued_val = getattr(target_record, accrued_field)
        
    assert isinstance(accrued_val, Decimal), f"Accrued interest value is not a Decimal: {accrued_val}"
    
    # We expect 648.147675. We assert that the value is close to the expected value to handle roundoff/truncation differences.
    expected_exact = Decimal("12345.67") * Decimal("0.0525")
    diff = abs(accrued_val - expected_exact)
    
    # Allow difference up to 0.01 to account for 2-decimal rounding or truncation (e.g. 648.14 or 648.15)
    assert diff <= Decimal("0.01"), f"Accrued interest calculation output incorrect. Expected close to {expected_exact}, got {accrued_val}"
    print(f"Functional calculation verified successfully. Output: {accrued_val}")
