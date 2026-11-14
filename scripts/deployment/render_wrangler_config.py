"""Generate the dedicated Cloudflare deployment config from CI variables.

The generated config is ignored by Git and rejects placeholders or malformed
account, D1, and release identifiers before it reaches Wrangler.
"""

import sys

from scripts.deployment.cloudflare_config import render_wrangler_config


def main() -> int:
    """Render a Wrangler config without changing the local template.

    Returns:
        Zero when the ignored deployment config was generated successfully.
    """
    try:
        path = render_wrangler_config()
    except (OSError, KeyError, ValueError) as exc:
        print(str(exc))
        return 1
    print(f"Rendered dedicated Wrangler configuration: {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
