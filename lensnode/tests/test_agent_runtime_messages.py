from lensnode.agent_runtime.messages import build_initial_messages
from lensnode.agent_runtime.direct_answer import _answer_general_chat_directly


def test_build_initial_messages_includes_current_images():
    messages = build_initial_messages(
        [],
        "What is wrong?",
        ["data:image/png;base64,encoded"],
    )

    assert messages[-1] == {
        "role": "user",
        "content": [
            {"type": "text", "text": "What is wrong?"},
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,encoded"},
            },
        ],
    }


def test_build_initial_messages_does_not_replay_history_for_images():
    messages = build_initial_messages(
        [{"role": "assistant", "content": "There is no image."}],
        "Describe this image.",
        ["data:image/png;base64,encoded"],
    )

    assert messages == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this image."},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,encoded"},
                },
            ],
        }
    ]


def test_direct_answer_includes_current_images():
    class Model:
        def invoke(self, messages, runtime_control_call=False):
            assert messages[-1].content[1]["type"] == "image_url"
            return type("Response", (), {"content": "Image described."})()

    answer = _answer_general_chat_directly(
        Model(),
        {
            "question": "Describe this image.",
            "image_data_urls": ["data:image/png;base64,encoded"],
        },
        "System prompt",
    )

    assert answer == "Image described."
