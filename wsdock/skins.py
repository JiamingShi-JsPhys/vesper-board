"""角色与换装的注册表。

一个「角色」可以有多个「换装」（比如小西有水手裙版和默认版），每个换装对应
一个素材目录，或者一个内置的矢量圆球。以后加新角色只需要在这里加一行。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Variant:
    key: str          # 存进 settings.pet_skin 的值：目录名 / "" 默认球 / "crest" 校徽球
    zh: str
    en: str
    kind: str = "skin"   # "skin" = assets/pet/<key>；"ball" = 代码画的圆球


@dataclass(frozen=True)
class Character:
    cid: str
    zh: str
    en: str
    variants: tuple[Variant, ...]

    @property
    def empty(self) -> bool:
        return not self.variants


def _ball(key: str, zh: str, en: str) -> Variant:
    return Variant(key, zh, en, "ball")


CHARACTERS: tuple[Character, ...] = (
    Character("vesper", "晚星看板", "Vesper Board", (
        Variant("icon", "图标球", "Icon ball", "icon"),
    )),
    Character("xiaoxi", "小西", "Xiaoxi", (
        Variant("mascot", "默认", "Default"),
    )),
)


def user_characters() -> list[Character]:
    """扫描用户目录里导入的形象：每个子目录要有 idle.png。"""
    from . import paths
    root = paths.pet_user_dir()
    out: list[Character] = []
    try:
        folders = sorted(p for p in root.iterdir() if p.is_dir() and (p / "idle.png").exists())
    except OSError:
        return out
    for folder in folders:
        glyph = "自定义" if lang_zh() else "Custom"
        out.append(Character("user:" + folder.name, folder.name, folder.name,
                             (Variant("user/" + folder.name, glyph, "Custom"),)))
    return out


def lang_zh() -> bool:
    try:
        from .i18n import LANG
        return LANG != "en"
    except Exception:
        return True


def all_characters() -> list[Character]:
    return list(CHARACTERS) + user_characters()


def label(character: Character, variant: Variant, lang: str) -> str:
    name = variant.en if lang == "en" else variant.zh
    if character.cid == "default":
        return name
    head = character.en if lang == "en" else character.zh
    return "%s · %s" % (head, name)


def all_variants() -> list[Variant]:
    out: list[Variant] = []
    for ch in CHARACTERS:
        out.extend(ch.variants)
    return out
