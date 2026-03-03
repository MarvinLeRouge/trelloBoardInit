#!/usr/bin/env python3
"""
trello_import.py — Import a Markdown todo list into Trello.

Usage:
    python trello_import.py tasks.md              # dry-run then confirm
    python trello_import.py tasks.md --force      # dry-run then auto-confirm
    python trello_import.py tasks.md --dry-run    # dry-run only, no prompt
    python trello_import.py tasks.md --board-id BOARD_ID  # use existing board
"""

import argparse
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

TRELLO_COLORS = [
    "green", "yellow", "orange", "red", "purple",
    "blue", "sky", "lime", "pink", "black"
]
VALID_COLORS = set(TRELLO_COLORS)

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(log_path: Path) -> logging.Logger:
    logger = logging.getLogger("trello_import")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger


# ---------------------------------------------------------------------------
# Markdown parser
# ---------------------------------------------------------------------------

FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def parse_markdown(filepath: Path) -> tuple[dict, list[dict]]:
    """
    Parse the markdown file.
    Returns (header, cards) where:
      header = { board, labels: [...] }
      cards  = [ { title, labels: [...], content } ]
    """
    raw = filepath.read_text(encoding="utf-8")

    # Extract global header (first front matter block)
    match = FRONT_MATTER_RE.match(raw)
    if not match:
        raise ValueError("No global YAML front matter found at the top of the file.")

    header = yaml.safe_load(match.group(1))
    if not isinstance(header.get("labels"), list):
        header["labels"] = []
    def normalize_labels(raw):
        result = []
        for l in raw:
            if isinstance(l, dict):
                result.append({"name": str(l.get("name", "")).strip(), "color": l.get("color")})
            elif isinstance(l, str) and l.startswith("{"):
                # Cas corrompu — ignorer silencieusement ou logger un warning
                continue
            else:
                result.append({"name": str(l).strip(), "color": None})
        return result

    header["labels"] = normalize_labels(header["labels"])
    rest = raw[match.end():].strip()

    # Extract individual cards
    card_pattern = re.compile(r"---\s*\n(.*?)\n---\s*\n(.*?)(?=\n---|\Z)", re.DOTALL)
    cards = []
    for m in card_pattern.finditer(rest):
        meta = yaml.safe_load(m.group(1))
        content = m.group(2).strip()
        if not meta or not meta.get("title"):
            continue
        labels = [str(l).strip() for l in meta.get("labels", [])]
        cards.append({
            "title": str(meta["title"]).strip(),
            "labels": labels,
            "content": content,
        })

    return header, cards


# ---------------------------------------------------------------------------
# Coherence check + auto-fix
# ---------------------------------------------------------------------------

def check_and_fix_labels(filepath: Path, header: dict, cards: list[dict], logger: logging.Logger) -> dict:
    """
    Collect all labels used in cards.
    If any are missing from the header, add them and rewrite the file.
    Returns updated header.
    """
    declared_names = {l["name"] for l in header["labels"]}
    used_names = set()
    for card in cards:
        used_names.update(card["labels"])

    missing = used_names - declared_names
    if not missing:
        logger.info("✅ Label coherence OK — all card labels are declared in header.")
        return header

    logger.warning(f"⚠️  Labels used in cards but missing from header: {sorted(missing)}")
    logger.info("   → Auto-fixing header in the markdown file...")

    for name in sorted(missing):
        header["labels"].append({"name": name, "color": None})

    # Sérialiser proprement : string si pas de couleur, dict imbriqué si couleur
    serialized_labels = []
    for l in header["labels"]:
        if l.get("color"):
            serialized_labels.append({"name": l["name"], "color": l["color"]})
        else:
            serialized_labels.append(l["name"])

    raw = filepath.read_text(encoding="utf-8")
    new_header_yaml = yaml.dump(
        {"board": header.get("board"), "labels": serialized_labels},
        default_flow_style=False,
        allow_unicode=True,
    ).strip()
    new_front = f"---\n{new_header_yaml}\n---"
    updated = FRONT_MATTER_RE.sub(new_front, raw, count=1)
    filepath.write_text(updated, encoding="utf-8")
    logger.info(f"   → File updated. Added labels: {sorted(missing)}")

    return header

# ---------------------------------------------------------------------------
# Trello API client
# ---------------------------------------------------------------------------

class TrelloClient:
    BASE = "https://api.trello.com/1"

    def __init__(self, api_key: str, token: str, logger: logging.Logger, dry_run: bool = False):
        self.auth = {"key": api_key, "token": token}
        self.logger = logger
        self.dry_run = dry_run

    def _get(self, path: str, params: dict = None) -> dict | list:
        r = requests.get(f"{self.BASE}{path}", params={**(params or {}), **self.auth})
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, data: dict = None) -> dict:
        if self.dry_run:
            return {}
        r = requests.post(f"{self.BASE}{path}", params=self.auth, json=data or {})
        r.raise_for_status()
        return r.json()

    def get_boards(self) -> list[dict]:
        return self._get("/members/me/boards", {"fields": "id,name,closed"})

    def get_board(self, board_id: str) -> dict:
        return self._get(f"/boards/{board_id}", {"fields": "id,name"})

    def create_board(self, name: str) -> dict:
        return self._post("/boards/", {"name": name, "defaultLists": "false"})

    def get_lists(self, board_id: str) -> list[dict]:
        return self._get(f"/boards/{board_id}/lists", {"fields": "id,name"})

    def create_list(self, board_id: str, name: str) -> dict:
        return self._post("/lists", {"name": name, "idBoard": board_id})

    def create_label(self, board_id: str, name: str, color: str | None) -> dict:
        return self._post("/labels", {"name": name, "color": color, "idBoard": board_id})

    # Et get_labels : ajouter "color" dans les fields
    def get_labels(self, board_id: str) -> list[dict]:
        return self._get(f"/boards/{board_id}/labels", {"fields": "id,name,color"})

    def delete_label(self, label_id: str) -> None:
        if self.dry_run:
            return
        r = requests.delete(f"{self.BASE}/labels/{label_id}", params=self.auth)
        r.raise_for_status()

    def get_cards(self, list_id: str) -> list[dict]:
        return self._get(f"/lists/{list_id}/cards", {"fields": "id,name"})

    def create_card(self, list_id: str, title: str, desc: str, label_ids: list[str]) -> dict:
        return self._post("/cards", {
            "name": title,
            "desc": desc,
            "idList": list_id,
            "idLabels": label_ids,
        })


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def run(
    filepath: Path,
    dry_run: bool,
    force: bool,
    board_id_override: str | None,
    api_key: str,
    token: str,
    logger: logging.Logger,
) -> bool:
    start = time.time()
    stats = {
        "board": None,
        "labels_created": 0,
        "labels_existing": 0,
        "cards_created": 0,
        "cards_skipped": 0,
        "errors": 0,
    }

    prefix = "[DRY-RUN] " if dry_run else ""

    logger.info("=" * 60)
    logger.info(f"{prefix}Starting trello_import — file: {filepath.name}")
    logger.info("=" * 60)

    # --- Passe 0: Parse & validate ---
    logger.info(f"{prefix}Passe 0 — Parsing & validation")
    try:
        header, cards = parse_markdown(filepath)
    except Exception as e:
        logger.error(f"❌ Failed to parse markdown: {e}")
        return False

    if not header.get("board") and not board_id_override:
        logger.error("❌ No 'board' name in header and no --board-id provided.")
        return False

    if not cards:
        logger.error("❌ No cards found in the file.")
        return False

    logger.info(f"   Board   : {header.get('board', '(using --board-id)')}")
    logger.info(f"   Labels  : {header['labels']}")
    logger.info(f"   Cards   : {len(cards)} found")

    # Label coherence check + auto-fix
    header = check_and_fix_labels(filepath, header, cards, logger)

    # Duplicate card title check — always blocking
    titles = [c["title"] for c in cards]
    duplicates = {t for t in titles if titles.count(t) > 1}
    if duplicates:
        logger.error(f"❌ Duplicate card titles in file: {duplicates}")
        logger.error("   → Fix your markdown file before proceeding.")
        return False
    logger.info("✅ No duplicate caurgentrd titles in file.")

    client = TrelloClient(api_key, token, logger, dry_run=dry_run)

    # --- Passe 1: Board ---
    logger.info(f"{prefix}Passe 1 — Board")

    if board_id_override:
        try:
            board = client.get_board(board_id_override)
            board_id = board["id"]
            logger.info(f"✅ Using existing board '{board.get('name')}' (--board-id)")
            stats["board"] = "existing (--board-id)"
        except Exception as e:
            logger.error(f"❌ Cannot fetch board {board_id_override}: {e}")
            return False
    else:
        board_name = header["board"]
        try:
            existing_boards = client.get_boards()
        except Exception as e:
            logger.error(f"❌ Cannot fetch boards: {e}")
            return False

        existing = next(
            (b for b in existing_boards if b["name"] == board_name and not b.get("closed")),
            None
        )

        if existing:
            board_id = existing["id"]
            logger.info(f"✅ Board '{board_name}' already exists — reusing.")
            stats["board"] = "existing"
        else:
            if dry_run:
                board_id = "DRY_RUN_BOARD_ID"
                logger.info(f"[DRY-RUN] 🏗️  Would create board '{board_name}'")
                stats["board"] = "would be created"
            else:
                try:
                    board = client.create_board(board_name)
                    board_id = board["id"]
                    logger.info(f"🏗️  Board '{board_name}' created.")
                    stats["board"] = "created"
                except Exception as e:
                    logger.error(f"❌ Failed to create board: {e}")
                    return False

    # Backlog list
    if dry_run:
        list_id = "DRY_RUN_LIST_ID"
        logger.info("[DRY-RUN] 📋 Would ensure 'Backlog' list exists.")
    else:
        try:
            lists = client.get_lists(board_id)
            backlog = next((l for l in lists if l["name"].lower() == "backlog"), None)
            if backlog:
                list_id = backlog["id"]
                logger.info("✅ 'Backlog' list already exists.")
            else:
                bl = client.create_list(board_id, "Backlog")
                list_id = bl["id"]
                logger.info("➕ 'Backlog' list created.")
        except Exception as e:
            logger.error(f"❌ Failed to get/create Backlog list: {e}")
            return False

    # Passe 1.5 — Nettoyage des labels par défaut (board neuf uniquement)
    if not dry_run and stats["board"] == "created":
        logger.info("Passe 1.5 — Cleaning default board labels")
        try:
            default_labels = client.get_labels(board_id)
            for dl in default_labels:
                if not dl.get("name"):  # labels vides = labels par défaut Trello
                    client.delete_label(dl["id"])
                    logger.info(f"🗑️  Deleted default empty label '{dl['id']}'")
        except Exception as e:
            logger.warning(f"⚠️  Could not clean default labels: {e}")

    # --- Passe 2: Labels ---
    logger.info(f"{prefix}Passe 2 — Labels")
    label_map = {}

    if dry_run:
        color_index = 0
        for label in header["labels"]:
            name = label["name"]
            color = label.get("color") or TRELLO_COLORS[color_index % len(TRELLO_COLORS)]
            if not label.get("color"):
                color_index += 1
            logger.info(f"[DRY-RUN] 🏷️  Would ensure label '{name}' (color: {color}).")
            label_map[name] = f"DRY_{name}"
    else:
        try:
            existing_labels = client.get_labels(board_id)
        except Exception as e:
            logger.error(f"❌ Cannot fetch labels: {e}")
            return False

        existing_map = {l["name"]: l for l in existing_labels if l.get("name")}
        existing_color_map = {l["name"]: l.get("color") for l in existing_labels if l.get("name")}

        color_index = 0
        for label in header["labels"]:
            name = label["name"]

            # Priorité : couleur déclarée > couleur existante sur le board > rotation auto
            color = label.get("color")
            if not color and name in existing_color_map:
                color = existing_color_map[name]
            if not color:
                color = TRELLO_COLORS[color_index % len(TRELLO_COLORS)]
                color_index += 1

            if name in existing_map:
                label_map[name] = existing_map[name]["id"]
                logger.info(f"✅ Label '{name}' already exists (color: {existing_map[name].get('color')}).")
                stats["labels_existing"] += 1
            else:
                try:
                    new_label = client.create_label(board_id, name, color)
                    label_map[name] = new_label["id"]
                    logger.info(f"➕ Label '{name}' created (color: {color}).")
                    stats["labels_created"] += 1
                except Exception as e:
                    logger.error(f"❌ Failed to create label '{name}': {e}")
                    stats["errors"] += 1

    # --- Passe 3: Cards ---
    logger.info(f"{prefix}Passe 3 — Cards")

    if dry_run:
        for i, card in enumerate(cards, 1):
            logger.info(
                f"[DRY-RUN] 🃏 Would create card {i}/{len(cards)}: '{card['title']}' "
                f"[labels: {card['labels']}]"
            )
    else:
        # Idempotence: check for existing cards BEFORE creating anything
        try:
            existing_cards = client.get_cards(list_id)
        except Exception as e:
            logger.error(f"❌ Cannot fetch existing cards: {e}")
            return False

        existing_titles = {c["name"] for c in existing_cards}
        would_duplicate = [c["title"] for c in cards if c["title"] in existing_titles]

        if would_duplicate:
            logger.error("❌ Cards already exist in Backlog (idempotence check — aborting):")
            for title in would_duplicate:
                logger.error(f"   • {title}")
            logger.error("   → Remove or rename duplicates in your markdown file.")
            return False

        for i, card in enumerate(cards, 1):
            label_ids = [label_map[l] for l in card["labels"] if l in label_map]
            try:
                client.create_card(list_id, card["title"], card["content"], label_ids)
                logger.info(f"✅ Card {i}/{len(cards)} '{card['title']}' created.")
                stats["cards_created"] += 1
            except Exception as e:
                logger.error(f"❌ Card {i}/{len(cards)} '{card['title']}' failed: {e}")
                stats["errors"] += 1

    # --- Summary ---
    elapsed = time.time() - start
    logger.info("")
    logger.info("=" * 60)
    logger.info(f"{prefix}RÉSUMÉ")
    logger.info("=" * 60)
    logger.info(f"  Board             : {stats['board'] or '(dry-run)'}")
    if not dry_run:
        logger.info(f"  Labels créés      : {stats['labels_created']}")
        logger.info(f"  Labels existants  : {stats['labels_existing']}")
        logger.info(f"  Cartes créées     : {stats['cards_created']}")
        logger.info(f"  Cartes ignorées   : {stats['cards_skipped']}")
        logger.info(f"  Erreurs           : {stats['errors']}")
    else:
        logger.info(f"  Cartes planifiées : {len(cards)}")
        logger.info(f"  Labels planifiés  : {len(header['labels'])}")
    logger.info(f"  Durée             : {elapsed:.2f}s")
    logger.info("=" * 60)

    return stats["errors"] == 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Import a Markdown todo list into Trello.")
    parser.add_argument("file", type=Path, help="Path to the markdown file")
    parser.add_argument("--dry-run", action="store_true", help="Validate only, do not create anything")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompt after dry-run")
    parser.add_argument("--board-id", dest="board_id", default=None, help="Use an existing Trello board ID")
    args = parser.parse_args()

    if not args.file.exists():
        print(f"❌ File not found: {args.file}")
        sys.exit(1)

    load_dotenv()
    api_key = os.getenv("TRELLO_API_KEY")
    token = os.getenv("TRELLO_TOKEN")
    if not api_key or not token:
        print("❌ TRELLO_API_KEY and TRELLO_TOKEN must be set in .env")
        sys.exit(1)

    log_filename = f"trello_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_path = Path("logs") / log_filename
    logger = setup_logging(log_path)
    logger.info(f"Log file: {log_path}")

    # Always run dry-run first
    logger.info(">>> Running dry-run first...")
    dry_ok = run(
        filepath=args.file,
        dry_run=True,
        force=args.force,
        board_id_override=args.board_id,
        api_key=api_key,
        token=token,
        logger=logger,
    )

    if not dry_ok:
        logger.error("❌ Dry-run failed. Fix the errors above before proceeding.")
        sys.exit(1)

    logger.info("✅ Dry-run passed.")

    # If --dry-run flag, stop here
    if args.dry_run:
        logger.info("--dry-run flag set. Stopping here.")
        sys.exit(0)

    # Confirmation prompt (unless --force)
    if not args.force:
        print("\n" + "=" * 60)
        print("Dry-run OK. Proceed with real creation? (y/N) ", end="")
        answer = input().strip().lower()
        if answer != "y":
            logger.info("Aborted by user.")
            print("Aborted.")
            sys.exit(0)

    # Real run
    logger.info(">>> Starting real import...")
    success = run(
        filepath=args.file,
        dry_run=False,
        force=args.force,
        board_id_override=args.board_id,
        api_key=api_key,
        token=token,
        logger=logger,
    )

    if not success:
        logger.error("❌ Import completed with errors. Check the log.")
        sys.exit(1)

    logger.info("🎉 Import completed successfully.")
    sys.exit(0)


if __name__ == "__main__":
    main()
