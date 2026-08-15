"""Visual board explanations: validation of model-generated board specs.

Every check in this package abstains rather than guesses. A check that cannot
parse what it is looking at reports nothing, following the ToolResult
is_equivalent-is-None convention used throughout app/math. A false rejection is
worse than a missing check: it makes the feature look broken to the student,
while a missing check leaves the board no worse than the prose the tutor would
otherwise have written.
"""
