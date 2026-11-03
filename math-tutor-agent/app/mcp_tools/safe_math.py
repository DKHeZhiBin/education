from __future__ import annotations

import ast
import re
from dataclasses import dataclass

import sympy as sp


MAX_EXPRESSION_LENGTH = 500
MAX_AST_NODES = 100
MAX_POWER = 12
VARIABLE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")


class UnsafeMathExpression(ValueError):
    """中文：定义“unsafe·math·expression”类，封装该职责相关的数据与行为。
    English: Defines the unsafe math expression class and encapsulates data and behavior for that responsibility.
    """
    pass


def normalize_expression(value: str) -> str:
    """中文：处理“规范化·expression”相关操作。
    English: Handles the normalize expression operation.
    """
    if not value or not value.strip():
        raise UnsafeMathExpression("表达式不能为空")
    if len(value) > MAX_EXPRESSION_LENGTH:
        raise UnsafeMathExpression("表达式过长")
    normalized = (
        value.strip()
        .replace("−", "-")
        .replace("–", "-")
        .replace("×", "*")
        .replace("÷", "/")
        .replace("^", "**")
        .replace("（", "(")
        .replace("）", ")")
        .replace("√", "sqrt")
    )
    normalized = re.sub(r"sqrt([A-Za-z0-9.]+)", r"sqrt(\1)", normalized)
    normalized = re.sub(r"\s+", "", normalized)
    normalized = re.sub(r"(?<=\d)(?=[A-Za-z(])", "*", normalized)
    normalized = re.sub(r"(?<=\))(?=[A-Za-z0-9(])", "*", normalized)
    normalized = re.sub(r"(?<!sqrt)(?<=[A-Za-z])(?=\()", "*", normalized)
    return normalized


def validate_variable(variable: str) -> str:
    """中文：处理“验证·variable”相关操作。
    English: Handles the validate variable operation.
    """
    if not VARIABLE_PATTERN.fullmatch(variable):
        raise UnsafeMathExpression("变量名不合法")
    return variable


class SafeSympyBuilder(ast.NodeVisitor):
    """中文：定义“safe·sympy·builder”类，封装该职责相关的数据与行为。
    English: Defines the safe sympy builder class and encapsulates data and behavior for that responsibility.
    """
    def __init__(self) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.symbols: dict[str, sp.Symbol] = {}
        self.node_count = 0

    def visit(self, node: ast.AST):
        """中文：处理“visit”相关操作。
        English: Handles the visit operation.
        """
        self.node_count += 1
        if self.node_count > MAX_AST_NODES:
            raise UnsafeMathExpression("表达式结构过于复杂")
        return super().visit(node)

    def visit_Expression(self, node: ast.Expression) -> sp.Expr:
        """中文：处理“visit·expression”相关操作。
        English: Handles the visit expression operation.
        """
        return self.visit(node.body)

    def visit_Name(self, node: ast.Name) -> sp.Symbol:
        """中文：处理“visit·name”相关操作。
        English: Handles the visit name operation.
        """
        validate_variable(node.id)
        return self.symbols.setdefault(node.id, sp.Symbol(node.id, real=True))

    def visit_Constant(self, node: ast.Constant) -> sp.Expr:
        """中文：处理“visit·constant”相关操作。
        English: Handles the visit constant operation.
        """
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise UnsafeMathExpression("只允许数字常量")
        if abs(float(node.value)) > 1_000_000_000:
            raise UnsafeMathExpression("数字超出允许范围")
        return sp.Integer(node.value) if isinstance(node.value, int) else sp.Float(node.value)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> sp.Expr:
        """中文：处理“visit·unary·op”相关操作。
        English: Handles the visit unary op operation.
        """
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.UAdd):
            return operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise UnsafeMathExpression("不支持该一元运算")

    def visit_BinOp(self, node: ast.BinOp) -> sp.Expr:
        """中文：处理“visit·bin·op”相关操作。
        English: Handles the visit bin op operation.
        """
        left = self.visit(node.left)
        right = self.visit(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Pow):
            if not right.is_number:
                raise UnsafeMathExpression("指数必须是数字常量")
            if abs(float(right)) > MAX_POWER:
                raise UnsafeMathExpression("指数超出允许范围")
            return left**right
        raise UnsafeMathExpression("不支持该运算")

    def visit_Call(self, node: ast.Call) -> sp.Expr:
        """中文：处理“visit·call”相关操作。
        English: Handles the visit call operation.
        """
        if (
            not isinstance(node.func, ast.Name)
            or node.func.id != "sqrt"
            or len(node.args) != 1
            or node.keywords
        ):
            raise UnsafeMathExpression("只允许使用单参数 sqrt 函数")
        return sp.sqrt(self.visit(node.args[0]))

    def generic_visit(self, node: ast.AST):
        """中文：处理“generic·visit”相关操作。
        English: Handles the generic visit operation.
        """
        raise UnsafeMathExpression(f"不支持的表达式结构：{type(node).__name__}")


def parse_expression(value: str) -> sp.Expr:
    """中文：处理“解析·expression”相关操作。
    English: Handles the parse expression operation.
    """
    normalized = normalize_expression(value)
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError as error:
        raise UnsafeMathExpression("表达式格式不正确") from error
    return SafeSympyBuilder().visit(tree)


@dataclass(frozen=True)
class ParsedEquation:
    """中文：定义“parsed·equation”类，封装该职责相关的数据与行为。
    English: Defines the parsed equation class and encapsulates data and behavior for that responsibility.
    """
    left: sp.Expr
    right: sp.Expr

    @property
    def residual(self) -> sp.Expr:
        """中文：处理“residual”相关操作。
        English: Handles the residual operation.
        """
        return sp.simplify(self.left - self.right)


def parse_equation(value: str) -> ParsedEquation:
    """中文：处理“解析·equation”相关操作。
    English: Handles the parse equation operation.
    """
    if value.count("=") != 1:
        raise UnsafeMathExpression("方程必须且只能包含一个等号")
    left, right = value.split("=", maxsplit=1)
    return ParsedEquation(parse_expression(left), parse_expression(right))


def display(value: sp.Expr | sp.Set) -> str:
    """中文：处理“display”相关操作。
    English: Handles the display operation.
    """
    return sp.sstr(value).replace("**", "^")
