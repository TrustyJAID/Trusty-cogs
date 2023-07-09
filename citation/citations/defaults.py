import pkg_resources


def _get_resource(file_name):
    return pkg_resources.resource_filename(__name__, f"data/{file_name}")


width = 183
height = 80
multiplier = 2  # Original game is 2x, not 1x

stamp_filename = _get_resource("moa.png")
stamp_bg_filename = _get_resource("stamp_bg.png")

main_font_file = _get_resource("BMmini.ttf")
alt_font_file = _get_resource("Megan_Serif.ttf")

penalty: str = "No penalty - warning issued"
title: str = "M.O.A. Citation"

barcode = [1, 1, 1, 2, 2]
barcode_str: str = "1,1,1,2,2"

theme = "pink"
