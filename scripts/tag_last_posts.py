API_BASE = "https://soybooru.com/api"
BOORU_POSTS = f"{API_BASE}/booru/posts"

def get_recent_moderation_users(auth):
    users = set()

    url = f"{API_BASE}/audit-logs"
    for action in ("Moderation.BanUser", "Moderation.UnbanUser"):
        res = auth.get(url, params={
            "page": 1,
            "pageSize": 5,
            "action": action,
            "category": "Moderation"
        })

        data = res.json()

        for item in data.get("items", []):
            username = item.get("targetId")

            if username:
                users.add(username)

    print(f"[*] Checked audit log most recents, found {len(users)} bans")
    return users

def get_latest_post(auth, username):
    res = auth.get(f"{API_BASE}/User/{username}/posts", params={
        "page": 1,
        "pageSize": 1,
    })
    res.raise_for_status()

    data = res.json()
    return data[0] if data else None

def format_tag(tag):
    category = tag.get("category")
    name = tag["name"]

    if category:
        return f"{category}:{name}"
    return name

def build_tag_payload(post):
    return [format_tag(tag) for tag in post.get("tags", [])]

def has_last_post_tag(post):
    return any(
        tag.get("category") == "meta"
        and tag.get("name") == "last_post"
        for tag in post.get("tags", [])
    )

def is_currently_permabanned(post):
    uploader = post.get("uploader") or {}

    for ban in uploader.get("activeBans", []):
        if (
            ban.get("zone") == "Sitewide"
            and str(ban.get("endTime", "")).startswith("9999-12-31")
        ):
            return True

    return False

def put_tags(auth, post_id, tags):
    auth.put(f"{BOORU_POSTS}/{post_id}/tags", json={
            "tags": tags
        })

def add_last_post_tag(auth, post):
    post_id = post["id"]

    tags = build_tag_payload(post)
    tags.append("meta:last_post")
    put_tags(auth, post_id, tags)

    print(f"[+] Tagged post #{post_id}: https://soybooru.com/post/view/{post_id}")
    return True

def remove_last_post_tag(auth, post):
    post_id = post["id"]

    tags = [
        tag for tag in build_tag_payload(post)
        if tag != "meta:last_post"
    ]
    put_tags(auth, post_id, tags)

    print(f"[+] Removed meta:last_post from #{post_id}: https://soybooru.com/post/view/{post_id}")
    return True

def sync_last_post_tag(auth, username):
    print(f"[*] Checking {username}")

    post = get_latest_post(auth, username)

    if not post:
        print(f"[-] No posts found: https://soybooru.com/user/{username}")
        return

    currently_permabanned = is_currently_permabanned(post)
    currently_tagged = has_last_post_tag(post)

    if currently_permabanned and not currently_tagged:
        add_last_post_tag(auth, post)
    elif not currently_permabanned and currently_tagged:
        remove_last_post_tag(auth, post)
    else:
        print(
            f"[-] No change needed for #{post["id"]} "
            f"(permabanned={currently_permabanned}, tagged={currently_tagged})"
        )

def tag_last_posts(auth):
    users = get_recent_moderation_users(auth)

    for username in sorted(users):
        sync_last_post_tag(auth, username)