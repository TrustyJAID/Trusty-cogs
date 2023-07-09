import math
import re
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont

from . import defaults, themes
from .enums import Align, Section


class Factory:
    """
    :param width: width of the image, works better if it's even
    :param min_height: minimal height of the image
    :param multiplier: image pixels size multiplier

    .. warnings:: The built in stamp only work with multiplier == 2
    """

    def __init__(
        self,
        theme=themes.named[defaults.theme],
        condensed: bool = False,
        use_alt_font: bool = False,
        main_font: str = defaults.main_font_file,
        alt_font: str = defaults.alt_font_file,
        stamp_filename=defaults.stamp_filename,
        stamp_background=defaults.stamp_bg_filename,
        width=defaults.width,
        min_height=defaults.height,
        multiplier: int = defaults.multiplier,
    ):
        self.width = width
        self.min_height = min_height
        self.multiplier = multiplier

        self.theme = theme

        self.use_alt_font = use_alt_font
        self.condensed = condensed

        self.min_lines = 3
        self.line_height = 10
        if self.condensed:
            self.min_lines = 4
            self.line_height = 9

        # Ideally, there should be a stack of stamp images/bitmaps that you can
        # just layer over one another.
        self.stamp_img_bg = Image.open(stamp_background)
        self.stamp_img = Image.open(stamp_filename)

        self.alt_font_file = alt_font
        self.body_font_file = main_font

        self.body_font = ImageFont.truetype(main_font, 16)
        if use_alt_font:
            self.title_font = ImageFont.truetype(alt_font, 16)
        else:
            self.title_font = self.body_font

        self.title_align = Align.LEFT

        # 0, 1 -> right, left
        if self._align_line(Section.TITLE) == Align.LEFT:
            self.barcode_align = Align.RIGHT
        elif self._align_line(Section.TITLE) == Align.RIGHT:
            self.barcode_align = Align.LEFT

        # Those should be set manually
        # WARNING: might not work properly with text wrapping! Proceed with caution
        self.body_align = 0  # 0, 1, 2 -> left, center, right
        self.wrap_by_char = False
        self.split_at_newline = False
        self.pattern = None

    def generate_file(self, filename, filetype="PNG", **options):
        img = self.generate_image(**options)
        img.save(filename, filetype)

    def generate_image(
        self, content: List[str], penalty: List[str], title: List[str], barcode: List[int] = ()
    ) -> Image.Image:
        """This method formats the lines in a proper way for
        the actual drawing method to work with them. Also
        makes sure things don't overflow."""

        height: int = self.min_height

        barcode_width = 2
        for stripe in barcode:
            barcode_width += stripe

        title = [item.upper() for item in title]
        if self.use_alt_font:
            title = [item.replace(" ", "    ") for item in title]
        title, title_height = self._process_lines(
            title, 1, margins={0: (11, 12 + barcode_width + 2)}
        )
        height += title_height

        lines, content_height = self._process_lines(content, self.min_lines)
        height += content_height

        penalty = [item.upper() for item in penalty]
        penalty, penalty_height = self._process_lines(penalty, 1)
        height += penalty_height

        img = Image.new(
            "RGB", (self.width * self.multiplier, height * self.multiplier), self.theme.background
        )
        draw = ImageDraw.Draw(img)
        self._generate(draw, height, lines, penalty, title, barcode)
        return img

    def _generate(
        self,
        draw: ImageDraw.ImageDraw,
        height: int,
        lines: List[str],
        penalty: List[str],
        title: List[str],
        barcode: List[int],
    ) -> None:
        """Internal method to draw on already generated image.

        Draws on supplied PIL.ImageDraw canvas. No promises if
        you use it on your own, the text might not fit. Use
        generate_file or generate_image instead.
        """

        stamp_y = height - 4 - 32 - (len(penalty) - 1) * self.line_height
        self._stamp(draw, stamp_y, self.stamp_img_bg)
        self._stamp(draw, stamp_y, self.stamp_img, self.theme.background)
        self._dots_row(draw, 0, (0, 0))
        self._roll(draw, height)
        self._rect(draw, self.width - 1, 0, self.width, height, self.theme.details)
        self._dots_row(draw, height - 1, (1, 0))

        barcode_width = self._print_barcode(draw, barcode)

        # Header separator line
        title_separator_y = 17 + (len(title) - 1) * self.line_height
        self._dots_row(draw, title_separator_y, (8, 10), self.theme.foreground)
        title_offset = 4
        title_margin = [11, 12]
        if self.use_alt_font:
            title_offset = 3
        if (
            self.title_align == Align.CENTER
            or self._align_line(Section.TITLE, 0) == self.barcode_align
        ):
            if self.barcode_align == Align.LEFT:
                title_margin[0] += barcode_width + 2
            elif self.barcode_align == Align.RIGHT:
                title_margin[1] += barcode_width + 2
        title_margin = (title_margin[0], title_margin[1])
        self._text_lines(
            draw, height, title[:1], title_offset, self.title_font, margin=title_margin
        )
        if len(title) > 1:
            self._text_lines(
                draw, height, title[1:], title_offset + self.line_height, self.title_font
            )

        self._text_lines(draw, height, lines, title_separator_y + 5)

        # Footer separator line
        if self.condensed:
            footer_separator_y: int = height - 22 - 1 - (len(penalty) - 1) * self.line_height
        else:
            footer_separator_y: int = height - 26 - 1 - (len(penalty) - 1) * self.line_height

        self._dots_row(draw, footer_separator_y, (8, 10), self.theme.foreground)

        self._text_lines(draw, height, penalty, -15, align=Align.CENTER, margin=(12, 11))

    def _process_lines(
        self, input_lines: List[str], min_lines: int, margin: Tuple[int, int] = None, margins=None
    ) -> Tuple[List[str], int]:
        """Splits supplied array of lines so that it will fit
        into the image. Outputs height added up, if any.
        """
        lines = []
        if self.split_at_newline:
            newlines = []
            for x in input_lines:
                newlines.extend(x.split("\n"))
            lines = newlines
        else:
            lines.extend(input_lines)

        newlines = []
        if margin is None:
            margin = (11, 12)
        for index, line in enumerate(lines):
            line_margin = margin
            if margins is not None and len(newlines) in margins:
                line_margin = margins[len(newlines)]
            out = self._trim_line_length(line, self.body_font, line_margin, self.wrap_by_char)
            newlines.append(out[0])
            while len(out[1]) != 0:
                line_margin = margin
                if margins is not None and len(newlines) in margins:
                    line_margin = margins[len(newlines)]
                out = self._trim_line_length(
                    out[1], self.body_font, line_margin, self.wrap_by_char
                )
                newlines.append(out[0])
        lines = newlines

        added_height = max(0, len(lines) - min_lines) * self.line_height
        return lines, added_height

    def _trim_line_length(
        self,
        text: str,
        font: ImageFont.ImageFont,
        margins: Tuple[int, int],
        wrap_by_char: bool = False,
        width: int = None,
    ):
        if width is None:
            width = self.width
        max_w = (width - margins[0] - margins[1]) * self.multiplier

        #  Let's get line length in chosen font
        top, left, bottom, right = font.getbbox(text=text)
        size = (bottom - top, right - left)
        # size = font.getsize(text)
        if size[0] <= max_w:
            return text, ""  # Yay, we can just return the whole string. Crisis averted
        #  Or maybe not

        chars = 0
        if self.pattern is None:
            self.pattern = re.compile(r"\W?[\w,'-]+\W?")
        match = re.search(self.pattern, text)

        if match is not None:
            top, left, bottom, right = font.getbbox(text=text[: match.end()])
            size = (bottom - top, right - left)
            # size = font.getsize(text[:match.end()])
        else:
            wrap_by_char = True

        if size[0] > max_w or wrap_by_char:  # Word is longer than string, whoops.
            if match is not None:
                chars = match.end()
            else:
                chars = len(text)

            while size[0] > max_w:
                top, left, bottom, right = font.getbbox(text=text[:chars])
                size = (bottom - top, right - left)
                # size = font.getsize(text[:chars])
                chars -= 1
            return text[:chars], text[chars:]

        while size[0] < max_w:
            # We don't have any words left! Let the by-char match take it over
            if match is None:
                break
            top, left, bottom, right = font.getbbox(text=text[: chars + match.start()])
            size = (bottom - top, right - left)
            # size = font.getsize(text[:chars + match.start()])
            # Checks if the start of the word is already past sensible mark.
            if size[0] > max_w:
                break
            top, left, bottom, right = font.getbbox(text=text[: chars + match.end()])
            size = (bottom - top, right - left)
            # size = font.getsize(text[:chars + match.end()])
            if size[0] > max_w:
                break
            chars += match.end()
            match = re.search(self.pattern, text[chars:])
        line = text[:chars]
        remaining = text[chars:]
        if remaining[0:1] == " ":
            remaining = remaining[1:]
        return line, remaining

    def _dots_row(
        self, draw: ImageDraw.ImageDraw, line: int, margin: Tuple[int, int], color: str = None
    ):
        m = self.multiplier
        if color is None:
            color = self.theme.details
        start = margin[0]
        end = self.width - 1 - margin[1]
        num = 0
        for x in range((end - start + 1) // 2 + 1):
            c = [
                start * m + num * m * 2,
                line * m,
                start * m + num * m * 2 + m - 1,
                line * m + m - 1,
            ]
            draw.rectangle(c, color)
            num += 1
        return

    def _rect(self, draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, color: str = None):
        m = self.multiplier
        if color is None:
            color = self.theme.details
        draw.rectangle((x * m, y * m, (x + w) * m - 1, (y + h) * m - 1), color)
        # The `- 1` here is to not have aliasing artifacts. Might
        # break if the chosen multiplier is not divisible by 2

    def _roll(self, draw: ImageDraw.ImageDraw, height: int):
        for x in range((height + 3) // 9):
            self._rect(draw, 2, 3 + 9 * x, 3, 3)
            self._rect(draw, self.width - 7, 3 + 9 * x, 3, 3)

    # Could be overriden/extended to provide per-line alignment
    def _align_line(self, segment, line: int = 0):
        if segment == Section.TITLE and self.title_align is not None:
            return self.title_align
        if segment == Section.FOOTER:
            return Align.CENTER
        return self.body_align

    def _text_lines(
        self,
        draw,
        height: int,
        text: List[str],
        offset: int,
        font: ImageFont.ImageFont = None,
        color: str = None,
        align: Align = Align.LEFT,
        margin: Tuple[int, int] = (11, 12),
    ):
        for index, line in enumerate(text):
            self._text_line(
                draw,
                height,
                line,
                index,
                offset,
                font,
                color,
                align,
                max_lines=len(text),
                margin=margin,
            )

    def _text_line(
        self,
        draw: ImageDraw.ImageDraw,
        height: int,
        text: str,
        line_num: int,
        offset: int,
        font: ImageFont.ImageFont = None,
        color: str = None,
        align: Align = Align.LEFT,
        max_lines: int = None,
        margin: Tuple[int, int] = (11, 12),
    ):
        mult = self.multiplier
        left_m = margin[0]
        right_m = margin[1]
        if color is None:
            color = self.theme.foreground
        if font is None:
            font = self.body_font

        if line_num > max_lines:
            raise ValueError("Line number is over the assigned maximum")

        if offset > 0:
            offset += line_num * self.line_height
        else:
            if max_lines is None:
                offset = height + offset - line_num * self.line_height
            else:
                offset = height + offset - (max_lines - line_num - 1) * self.line_height

        top, left, bottom, right = font.getbbox(text=text)
        size = (bottom - top, right - left)
        # size = self.body_font.getsize(text)
        if align == Align.LEFT:
            draw.text((left_m * mult - 1, offset * mult), text, font=font, fill=color)
            return
        elif align == Align.CENTER:
            x = (self.width - left_m + right_m - (size[0] // mult)) // 2
            draw.text((x * mult - 1, offset * mult), text, font=font, fill=color)
            return
        elif align == Align.RIGHT:
            x = self.width - right_m - (size[0] // mult)
            draw.text((x * mult - 1, offset * mult), text, font=font, fill=color)
            return
        raise ValueError("Invalid alignment mode")

    def _stamp(
        self, draw: ImageDraw.ImageDraw, position: int, img: Image.Image, color: str = None
    ):  # 32x32 at 150x44
        if color is None:
            color = self.theme.details
        draw.bitmap(
            ((self.width * self.multiplier - img.width) // 2 - 1, position * self.multiplier),
            img,
            color,
        )

    def _print_barcode(self, draw: ImageDraw.ImageDraw, spec: List[int], color: str = None):
        if color is None:
            color = self.theme.foreground
        end = self.width - 11
        width = 2
        for x in spec:
            width += 1 + x
        offset = 0
        if self.barcode_align == Align.RIGHT:
            for x in reversed(spec):
                self._rect(draw, end - offset - x, 3, x, 6, color)
                offset += 1 + x
            self._rect(draw, end - offset - 2, 3, 2, 3, color)
        elif self.barcode_align == Align.LEFT:
            end = 11
            for x in spec:
                self._rect(draw, end + offset, 3, x, 6, color)
                offset += 1 + x
            self._rect(draw, end + offset, 3, 2, 3, color)
        else:
            raise AttributeError("Unsupported barcode alignment value")
        return offset + 2
