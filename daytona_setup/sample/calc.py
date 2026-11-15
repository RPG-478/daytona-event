"""DSH とテスト実行の動作確認に使う、いちばん小さなサンプル。"""


def add(a: float, b: float) -> float:
    return a + b


def divide(a: float, b: float) -> float:
    if b == 0:
        raise ZeroDivisionError("0 では割れません")
    return a / b
