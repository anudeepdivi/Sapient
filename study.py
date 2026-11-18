"""The study, in one place: which ADaM datasets the pipeline can build, what each one
reads, and how each one starts. Everything that needs to know (program header, prompts,
execution order, the gate) reads it from here.

Today this is the CDISC pilot, written out by hand. Pointing Sapient at another study
means replacing this table (CLAUDE.md item 32: load it from a study file).
"""
from dataclasses import dataclass
from pathlib import Path

from config import BASE_DIR, SDTM_SOURCE

ADAM_PREFIX = "data/adam/"  # an input under here is a parent ADaM, built earlier in the same run
DERIVATIONS_DIR = BASE_DIR / "templates" / "derivations"


@dataclass(frozen=True)
class Dataset:
    # (R variable name, repo-relative path). Real, case-correct locations, not written by
    # the model: wrong-case and wrong-directory filename bugs are impossible by construction.
    inputs: tuple[tuple[str, str], ...]
    # Where per-variable generation starts: the population filter and the parent merge.
    spine: str
    # Hand-written derivation body the pipeline graph splices in instead of asking the
    # model. Scaffolding, not the product.
    handwritten_body: Path | None = None

    @property
    def parents(self) -> set[str]:
        return {Path(path).stem for _, path in self.inputs if path.startswith(ADAM_PREFIX)}


DATASETS: dict[str, Dataset] = {
    "ADSL": Dataset(
        inputs=(("dm", f"{SDTM_SOURCE}/DM.xpt"), ("ex", f"{SDTM_SOURCE}/EX.xpt"), ("ds", f"{SDTM_SOURCE}/DS.xpt"),
                ("vs", f"{SDTM_SOURCE}/VS.xpt"), ("mh", f"{SDTM_SOURCE}/MH.xpt"), ("sv", f"{SDTM_SOURCE}/SV.xpt"),
                # QS/SC come from the CDISC pilot SDTM (pharmaversesdtm has no pilot QS/SC);
                # needed for EFFFL/MMSETOT (QS) and EDUCLVL (SC)
                ("qs", f"{SDTM_SOURCE}/QS.xpt"), ("sc", f"{SDTM_SOURCE}/SC.xpt")),
        spine='''result <- dm |>
  filter(ACTARMCD != "SCRNFAIL", ARMCD != "SCRNFAIL", !grepl("SCREEN", toupper(ARM)))''',
        handwritten_body=DERIVATIONS_DIR / "ADSL.R"),
    "ADAE": Dataset(
        inputs=(("sdtm", f"{SDTM_SOURCE}/AE.xpt"), ("adsl", "data/adam/ADSL.xpt")),
        spine='''adsl_vars <- adsl |>
  dplyr::transmute(STUDYID, USUBJID, SITEID, TRTSDT, TRTEDT, AGE, AGEGR1, AGEGR1N,
                   RACE, RACEN, SEX, SAFFL, TRTA = TRT01A, TRTAN = TRT01AN)

result <- sdtm |>
  filter(!is.na(AETERM)) |>
  derive_vars_merged(dataset_add = adsl_vars, by_vars = exprs(STUDYID, USUBJID))''',
        handwritten_body=DERIVATIONS_DIR / "ADAE.R"),
    "ADLBC": Dataset(
        inputs=(("sdtm", f"{SDTM_SOURCE}/LB.xpt"), ("adsl", "data/adam/ADSL.xpt")),
        spine='''adsl_vars <- adsl |>
  dplyr::transmute(STUDYID, USUBJID, SUBJID, TRTSDT, TRTEDT, AGE, AGEGR1, AGEGR1N,
                   RACE, RACEN, SEX, SAFFL, COMP24FL, DSRAEFL,
                   TRTP = TRT01P, TRTPN = TRT01PN, TRTA = TRT01A, TRTAN = TRT01AN)

result <- sdtm |>
  filter(LBCAT == "CHEMISTRY") |>
  derive_vars_merged(dataset_add = adsl_vars, by_vars = exprs(STUDYID, USUBJID))'''),
}


def parents(dataset: str) -> set[str]:
    """The ADaM datasets this one reads; empty for a dataset the study does not define."""
    return DATASETS[dataset].parents if dataset in DATASETS else set()
