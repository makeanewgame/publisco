#!/usr/bin/env python3
"""Publisco Trello board'u için küçük CLI (yalnızca stdlib).

Kimlik bilgileri repo kökündeki gitignore'lu `.env.trello`'dan okunur
(TRELLO_API_KEY, TRELLO_TOKEN); aynı adlı ortam değişkenleri önceliklidir.

  python3 scripts/trello.py lists
  python3 scripts/trello.py find "<metin>"
  python3 scripts/trello.py show <kart>
  python3 scripts/trello.py add "<Liste>" "<başlık>" [--desc METİN | --desc-file DOSYA] [--labels a,b]
  python3 scripts/trello.py move <kart> "<Liste>"
  python3 scripts/trello.py comment <kart> "<metin>"

<kart>: kart URL'i, shortLink (ör. AbCd1234) ya da kart id'si.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BOARD = "yt7AU8Yu"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _auth():
    env = {}
    path = os.path.join(ROOT, ".env.trello")
    if os.path.exists(path):
        for line in open(path):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.strip().split("=", 1)
                env[k] = v
    env.update({k: os.environ[k] for k in ("TRELLO_API_KEY", "TRELLO_TOKEN") if k in os.environ})
    if not env.get("TRELLO_API_KEY") or not env.get("TRELLO_TOKEN"):
        sys.exit(f"TRELLO_API_KEY/TRELLO_TOKEN bulunamadı ({path} ya da ortam değişkeni)")
    return {"key": env["TRELLO_API_KEY"], "token": env["TRELLO_TOKEN"]}


def call(method, path, **params):
    query = urllib.parse.urlencode({**params, **_auth()})
    url = f"https://api.trello.com/1{path}"
    if method == "GET":
        req = urllib.request.Request(f"{url}?{query}")
    else:
        req = urllib.request.Request(url, data=query.encode(), method=method)
    try:
        return json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {path} -> {e.code}: {e.read().decode()[:300]}")


def board_lists():
    return {l["name"]: l["id"] for l in call("GET", f"/boards/{BOARD}/lists")}


def board_labels():
    return {l["name"]: l["id"] for l in call("GET", f"/boards/{BOARD}/labels") if l["name"]}


def card_ref(ref):
    m = re.search(r"trello\.com/c/([A-Za-z0-9]+)", ref)
    return m.group(1) if m else ref


def resolve_list(name):
    lists = board_lists()
    if name not in lists:
        sys.exit(f"Liste yok: {name!r}. Mevcut: {', '.join(lists)}")
    return lists[name]


def cmd_lists(_):
    names = {v: k for k, v in board_lists().items()}
    counts = {}
    for c in call("GET", f"/boards/{BOARD}/cards", fields="idList"):
        counts[c["idList"]] = counts.get(c["idList"], 0) + 1
    for lid, name in names.items():
        print(f"{name}: {counts.get(lid, 0)} kart")
    print("etiketler:", ", ".join(board_labels()))


def cmd_find(a):
    names = {v: k for k, v in board_lists().items()}
    needle = a.text.casefold()
    for c in call("GET", f"/boards/{BOARD}/cards", fields="name,desc,idList,shortUrl"):
        if needle in c["name"].casefold() or needle in c["desc"].casefold():
            print(f"{c['shortUrl']}  [{names.get(c['idList'], '?')}]  {c['name']}")


def cmd_show(a):
    c = call("GET", f"/cards/{card_ref(a.card)}", fields="name,desc,idList,shortUrl,labels", list="true")
    print(f"{c['name']}\n{c['shortUrl']}  [{c['list']['name']}]  etiketler: {', '.join(l['name'] for l in c['labels']) or '-'}\n")
    print(c["desc"])


def cmd_add(a):
    desc = open(a.desc_file).read() if a.desc_file else (a.desc or "")
    labels = board_labels()
    wanted = [x.strip() for x in a.labels.split(",") if x.strip()] if a.labels else []
    missing = [x for x in wanted if x not in labels]
    if missing:
        sys.exit(f"Etiket yok: {missing}. Mevcut: {', '.join(labels)}")
    c = call("POST", "/cards", idList=resolve_list(a.list), name=a.title, desc=desc, pos=a.pos,
             idLabels=",".join(labels[x] for x in wanted))
    print(c["shortUrl"])


def cmd_move(a):
    c = call("PUT", f"/cards/{card_ref(a.card)}", idList=resolve_list(a.list), pos="top")
    print(f"{c['shortUrl']} -> {a.list}")


def cmd_comment(a):
    call("POST", f"/cards/{card_ref(a.card)}/actions/comments", text=a.text)
    print("yorum eklendi")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("lists").set_defaults(fn=cmd_lists)
    s = sub.add_parser("find"); s.add_argument("text"); s.set_defaults(fn=cmd_find)
    s = sub.add_parser("show"); s.add_argument("card"); s.set_defaults(fn=cmd_show)
    s = sub.add_parser("add")
    s.add_argument("list"); s.add_argument("title")
    g = s.add_mutually_exclusive_group(); g.add_argument("--desc"); g.add_argument("--desc-file")
    s.add_argument("--labels"); s.add_argument("--pos", default="top", choices=["top", "bottom"])
    s.set_defaults(fn=cmd_add)
    s = sub.add_parser("move"); s.add_argument("card"); s.add_argument("list"); s.set_defaults(fn=cmd_move)
    s = sub.add_parser("comment"); s.add_argument("card"); s.add_argument("text"); s.set_defaults(fn=cmd_comment)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
