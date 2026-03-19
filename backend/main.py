from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


class ImproveRequest(BaseModel):
    prompt: str = Field(..., description="Original user prompt")


class Issue(BaseModel):
    type: str
    description: str


class ImproveResponse(BaseModel):
    issues: List[Issue]
    improved_prompt: str


app = FastAPI(title="Prompt Coach API")

# Allow the local Chrome-extension flow during MVP development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def detect_issues(prompt: str) -> List[Issue]:
    """Generate 2-3 simple issues from the prompt using basic rules."""
    cleaned_prompt = prompt.strip()
    issues: List[Issue] = []

    if not cleaned_prompt:
        return [
            Issue(
                type="\uC785\uB825 \uC5C6\uC74C",
                description="\uD504\uB86C\uD504\uD2B8 \uB0B4\uC6A9\uC774 \uBE44\uC5B4 \uC788\uC5B4 \uC694\uCCAD \uC758\uB3C4\uB97C \uD30C\uC545\uD560 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4.",
            ),
            Issue(
                type="\uBAA9\uC801 \uBD88\uBA85\uD655",
                description="\uBB34\uC5C7\uC744 \uC5BB\uACE0 \uC2F6\uC740\uC9C0 \uBAA9\uD45C\uAC00 \uAD6C\uCCB4\uC801\uC73C\uB85C \uB4DC\uB7EC\uB098\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.",
            ),
        ]

    if len(cleaned_prompt) < 20:
        issues.append(
            Issue(
                type="\uB9E5\uB77D \uBD80\uC871",
                description="\uC124\uBA85\uC774 \uC9E7\uC544\uC11C \uD544\uC694\uD55C \uBC30\uACBD \uC815\uBCF4\uAC00 \uBD80\uC871\uD560 \uC218 \uC788\uC2B5\uB2C8\uB2E4.",
            )
        )

    goal_keywords = (
        "\uC124\uBA85",
        "\uC815\uB9AC",
        "\uBE44\uAD50",
        "\uC791\uC131",
        "\uCD94\uCC9C",
        "\uBD84\uC11D",
        "\uD574\uC918",
        "explain",
        "write",
        "compare",
        "recommend",
        "analyze",
    )
    if not any(keyword in cleaned_prompt for keyword in goal_keywords):
        issues.append(
            Issue(
                type="\uBAA9\uC801 \uBD88\uBA85\uD655",
                description="\uC6D0\uD558\uB294 \uACB0\uACFC\uBB3C\uC774 \uBB34\uC5C7\uC778\uC9C0 \uBA85\uD655\uD558\uAC8C \uB4DC\uB7EC\uB098\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.",
            )
        )

    format_keywords = (
        "\uC608\uC2DC",
        "\uB2E8\uACC4",
        "\uBAA9\uB85D",
        "\uD45C",
        "\uC694\uC57D",
        "\uD615\uC2DD",
        "\uAE38\uC774",
        "example",
        "step",
        "table",
        "summary",
        "format",
    )
    if not any(keyword in cleaned_prompt for keyword in format_keywords):
        issues.append(
            Issue(
                type="\uCD9C\uB825 \uD615\uC2DD \uBD80\uC871",
                description="\uB2F5\uBCC0\uC744 \uC5B4\uB5A4 \uD615\uD0DC\uB85C \uBC1B\uACE0 \uC2F6\uC740\uC9C0 \uC870\uAC74\uC774 \uBD80\uC871\uD569\uB2C8\uB2E4.",
            )
        )

    audience_keywords = (
        "\uCD08\uBCF4\uC790",
        "\uD559\uC0DD",
        "\uAC1C\uBC1C\uC790",
        "\uB3C5\uC790",
        "\uC0AC\uC6A9\uC790",
        "\uC2E4\uBB34\uC790",
        "beginner",
        "student",
        "developer",
        "user",
    )
    if not any(keyword in cleaned_prompt for keyword in audience_keywords):
        issues.append(
            Issue(
                type="\uB300\uC0C1 \uBD80\uC871",
                description="\uB2F5\uBCC0\uC744 \uB204\uAD6C \uAE30\uC900\uC73C\uB85C \uB9DE\uCD9C\uC9C0 \uB300\uC0C1 \uC815\uBCF4\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.",
            )
        )

    if not issues:
        issues.append(
            Issue(
                type="\uC138\uBD80 \uC870\uAC74 \uBCF4\uAC15 \uD544\uC694",
                description="\uAE30\uBCF8 \uC758\uB3C4\uB294 \uBCF4\uC774\uC9C0\uB9CC \uACB0\uACFC \uD488\uC9C8\uC744 \uB192\uC774\uB824\uBA74 \uC870\uAC74\uC744 \uB354 \uAD6C\uCCB4\uD654\uD558\uB294 \uAC8C \uC88B\uC2B5\uB2C8\uB2E4.",
            )
        )

    return issues[:3]


def build_improved_prompt(prompt: str) -> str:
    """Return a more detailed prompt based on the original input."""
    cleaned_prompt = prompt.strip()

    if not cleaned_prompt:
        return (
            "\uC8FC\uC81C, \uBAA9\uC801, \uB300\uC0C1 \uB3C5\uC790, \uC6D0\uD558\uB294 \uB2F5\uBCC0 \uD615\uC2DD\uC744 \uD3EC\uD568\uD574 \uD504\uB86C\uD504\uD2B8\uB97C \uB2E4\uC2DC \uC791\uC131\uD574\uC918. "
            "\uC608\uC2DC 1\uAC1C\uC640 \uB9C8\uC9C0\uB9C9 \uC694\uC57D\uB3C4 \uD568\uAED8 \uD3EC\uD568\uD574\uC918."
        )

    return "\n".join(
        [
            "\uB2E4\uC74C \uC694\uCCAD\uC744 \uB354 \uAD6C\uCCB4\uC801\uC774\uACE0 \uC2E4\uD589 \uAC00\uB2A5\uD558\uAC8C \uB2F5\uBCC0\uD574\uC918.",
            f"\uC6D0\uBCF8 \uC694\uCCAD: {cleaned_prompt}",
            "",
            "\uC544\uB798 \uC870\uAC74\uC744 \uC9C0\uCF1C\uC918:",
            "1. \uC0AC\uC6A9\uC790\uC758 \uD575\uC2EC \uBAA9\uC801\uC744 \uD55C \uBB38\uC7A5\uC73C\uB85C \uBA3C\uC800 \uC815\uB9AC\uD558\uAE30",
            "2. \uD575\uC2EC \uB0B4\uC6A9\uC744 \uB2E8\uACC4 \uB610\uB294 \uBAA9\uB85D \uD615\uD0DC\uB85C \uAD6C\uC131\uD558\uAE30",
            "3. \uAD6C\uCCB4\uC801\uC778 \uC608\uC2DC\uB97C 1\uAC1C \uD3EC\uD568\uD558\uAE30",
            "4. \uB9C8\uC9C0\uB9C9\uC5D0 \uC9E7\uC740 \uC694\uC57D\uC744 \uCD94\uAC00\uD558\uAE30",
        ]
    )


@app.post("/improve", response_model=ImproveResponse)
def improve_prompt(request: ImproveRequest) -> ImproveResponse:
    """Analyze the prompt and return issues plus an improved version."""
    return ImproveResponse(
        issues=detect_issues(request.prompt),
        improved_prompt=build_improved_prompt(request.prompt),
    )
