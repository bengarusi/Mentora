from app.math.calculator import BasicCalculatorService


def test_exponentiation_is_rejected():
    assert BasicCalculatorService().evaluate("9**9**9") is None


def test_overlong_expression_is_rejected():
    assert BasicCalculatorService().evaluate("1+" * 300 + "1") is None
