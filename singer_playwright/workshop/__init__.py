"""Playwright scraper workshop for AI-driven iterative development."""

from singer_playwright.workshop.brief import Brief, evaluate_success, load_brief
from singer_playwright.workshop.codegen import compile_recipe, compile_recipe_file
from singer_playwright.workshop.schema import infer_schema_from_records
from singer_playwright.workshop.recipe import Recipe, load_recipe, replay_recipe, save_recipe

__all__ = [
    "Brief",
    "Recipe",
    "compile_recipe",
    "compile_recipe_file",
    "evaluate_success",
    "infer_schema_from_records",
    "load_brief",
    "load_recipe",
    "replay_recipe",
    "save_recipe",
]
