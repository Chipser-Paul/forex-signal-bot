# Security History Notice — Historical Fernet Key

**Status: advisory record only. No credential is reproduced here. No rotation,
history rewrite or destructive remote operation is authorized by this document.**

## Facts

1. A Fernet key file historically existed at repository path
   `frontend/session_key.key` and was committed to this repository's Git
   history. It remains retrievable from **older published remote history**
   (three historical commits on pre-existing branches touch that path).
2. The current Phase 8 canonical tree (this branch and its sanitized base)
   does **not** contain the key and does **not** inherit any reachable commit
   that contains it: the canonical branch is rooted at the parentless sanitized
   snapshot `1c593f5e14597b6b25a8abe702457e71a10e545c`, whose reachable history
   is exactly one commit.
3. Current production code does not use this key. The validation tree enforces
   a no-MT5/no-network import firewall in its tests, and no production module
   references the historical path. The only in-tree occurrences of the string
   are `.gitignore` guard rules.
4. A metadata-only inspection (paths, sizes, timestamps — no decryption, no
   content reads) of both local worktrees found **no ignored local session
   artifact that depends on the exposed key**.
5. Therefore the key must be treated as **permanently exposed and must never
   be reused** for any new session encryption, deployment secret or credential
   material.
6. Removing the key from the older published branches is a **destructive
   remote-history rewrite** and remains a separate, owner-authorized task.
   It is deliberately out of scope for the Phase 8 consolidation.
