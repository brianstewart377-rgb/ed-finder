"""Regression test for CLAUDE.md's documented pre-merge review-bot check.

Codex Review findings on PR #432: the originally documented command only
queried /pulls/<n>/comments (inline review comments), silently missing any
finding the bot places only in the top-level review body
(/pulls/<n>/reviews), and it didn't pass --paginate, so PRs with more than
one page of comments (30+) would silently drop later findings. Both gaps
mean "checked the bot" could pass while the actual review output was
incomplete. This pins the fix so the guidance can't quietly regress back to
either gap.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _claude_md() -> str:
    return (ROOT / 'CLAUDE.md').read_text(encoding='utf-8')


def test_documented_check_covers_inline_comments_endpoint():
    doc = _claude_md()

    assert 'pulls/<n>/comments' in doc
    assert '--paginate' in doc


def test_documented_check_covers_top_level_review_endpoint():
    doc = _claude_md()

    assert 'pulls/<n>/reviews' in doc


def test_documented_check_explicitly_requires_pagination_on_both_endpoints():
    doc = _claude_md()
    review_bullet_start = doc.index('chatgpt-codex-connector')
    review_bullet_end = doc.index('\n', review_bullet_start + 2000)
    bullet = doc[review_bullet_start:review_bullet_end]

    assert bullet.count('--paginate') >= 2, (
        'both the /comments and /reviews commands in this bullet must pass '
        '--paginate, or a PR with more than one page of results silently '
        'drops later findings'
    )
