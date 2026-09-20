from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from ensemble_utils import DEFAULT_ENSEMBLE_WEIGHTS, load_ensemble_weights

import pandas as pd

from page_output import write_page
from ui_locale import column_label, localize_mapping_for_display
from ui_theme import (
    ALIGN_LEFT,
    ALIGN_RIGHT,
    app_shell_close,
    app_shell_open,
    card,
    dataframe_table,
    definition_table,
    page_header,
    raw_details,
    write_stylesheet
)
from css_links import stylesheet_link
from web_security import security_meta_tags

logger = logging.getLogger(__name__)

# NOTE: remainder of file restored from last known-good revision;
# only the stylesheet_link import path was changed for parallel CSS loads.
