"""Controlled response-reflection check for a local training target."""
import argparse
import html


def check_reflection(response_text, probe):
    return {"reflected_unescaped": probe in response_text, "encoded_probe": html.escape(probe)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--response", default="Search results for: &lt;script&gt;test&lt;/script&gt;")
    parser.add_argument("--probe", default="<script>test</script>")
    args = parser.parse_args()
    print(check_reflection(args.response, args.probe))


if __name__ == "__main__":
    main()
