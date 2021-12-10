# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
# import os
# import sys
# sys.path.insert(0, os.path.abspath('.'))

import os
import sys

import django

sys.path.insert(0, os.path.join(os.path.abspath('.'), '../../backend'))
os.environ['DJANGO_SETTINGS_MODULE'] = 'MrMap.settings'
# Get an instance of a logger
from MrMap.settings import LOG_DIR

# create log dir if it does not exist
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

django.setup()

import sphinx_rtd_theme  # noqa

# -- Project information -----------------------------------------------------

project = 'MrMap'
copyright = '2021, mrmap-community'
author = 'mrmap-community'

# The full version, including alpha/beta/rc tags
release = 'v0.0.0'

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    'sphinx.ext.autodoc',
    'sphinx_rtd_theme',
    'sphinx_multiversion',
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = []

# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = "sphinx_rtd_theme"

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".

#html_static_path = ['_static']

linkcheck_ignore = [r'http://localhost\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)', r'https://localhost\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)', r'http://127.0.0.1\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)',
                    r'https://127.0.0.1\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)', r'http://YOUR-IP-ADDRESS\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)', ]

master_doc = "index"

# to get docstrings from django code, the django project needs to setup fist
from sphinx.builders.html import StandaloneHTMLBuilder
StandaloneHTMLBuilder.supported_image_types = [
    'image/svg+xml',
    'image/gif',
    'image/png',
    'image/jpeg'
]


smv_tag_whitelist = r'^v\d+\.\d+$'                # Include tags like "v2.1"
smv_branch_whitelist = r'^develop$'              # Include develop branch
# Use branches from all remotes
smv_remote_whitelist = None
