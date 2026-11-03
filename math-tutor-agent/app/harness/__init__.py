from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.harness.math_tutor import MathTutorAgentHarness

__all__ = ["MathTutorAgentHarness"]


def __getattr__(name: str):
    """中文：处理“__getattr__”相关操作。
    English: Handles the __getattr__ operation.
    """
    if name == "MathTutorAgentHarness":
        from app.harness.math_tutor import MathTutorAgentHarness

        return MathTutorAgentHarness
    raise AttributeError(name)
