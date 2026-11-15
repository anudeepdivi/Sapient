

from llm import complete
from config import CODEGEN_MODEL, HARNESS_GENERATOR
from r_layer.deterministic_checks import strip_markdown_fences

IMPL_PLACEHOLDER = "__IMPL_PATH__"

STUBS = {
    ("derive_special_response_flag", "implementation"): """\
derive_special_response_flag <- function(data, response_col = "AVALC") {
  data %>% mutate(SPECIALRSPFL = if_else(.data[[response_col]] %in% c("CR", "PR"), "Y", NA_character_))
}
""",
    ("derive_special_response_flag", "tests"): """\
library(dplyr)
library(testthat)
source("__IMPL_PATH__")

test_that("derive_special_response_flag flags complete and partial response only", {
  d <- data.frame(USUBJID = c("S1", "S2", "S3", "S4"),
                  AVALC   = c("CR", "PR", "SD", "PD"))
  out <- derive_special_response_flag(d)
  expect_equal(out$SPECIALRSPFL, c("Y", "Y", NA_character_, NA_character_))
})
""",
}

_PROMPTS = {
    "implementation": (
        "You are writing a reusable R function for a sponsor's clinical programming library.\n"
        "Capability name: {name}\n"
        "Purpose: {purpose}\n"
        "Return ONLY the R function definition named {name}. "
        "It must be self-contained (it may use dplyr). No examples, no explanation."
    ),
    "tests": (
        "You are writing testthat tests for the R function `{name}` ({purpose}).\n"
        "The first lines of the file MUST be:\n"
        "library(dplyr)\nlibrary(testthat)\nsource(\"{placeholder}\")\n"
        "Then write test_that() blocks covering normal and edge-case behavior. "
        "Return ONLY the test file content, no explanation."
    ),
}


def _llm(kind, capability):
    name = _capability_name(capability)
    prompt = _PROMPTS[kind].format(
        name=name, purpose=capability.get("purpose") or name,
        placeholder=IMPL_PLACEHOLDER,
    )
    return strip_markdown_fences(complete(prompt, CODEGEN_MODEL, timeout=60.0).text.strip())


def _capability_name(capability):
    return capability.get("name") or capability.get("capability")


def generate(kind, capability, generator=None):
    generator = generator or HARNESS_GENERATOR
    if generator == "stub":
        return STUBS[(_capability_name(capability), kind)]
    return _llm(kind, capability)
