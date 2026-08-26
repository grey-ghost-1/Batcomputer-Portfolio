"""Local text assistant with simple intent routing."""
import argparse


def reply(message):
    text = " ".join(message.lower().split())
    if text in {"hi", "hello", "hey"}:
        return "Hello. Alfred is online and ready to help."
    if "status" in text or "health" in text:
        return "All systems nominal."
    if "help" in text or "capabilities" in text:
        return "I can answer status, portfolio, and technical guidance questions."
    return "Please clarify the technical task you want help with."


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("message", nargs="*", default=["hello"])
    print(reply(" ".join(parser.parse_args().message)))
