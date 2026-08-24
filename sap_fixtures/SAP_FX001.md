# Statistical Analysis Plan — Protocol FX-001

> SYNTHETIC PUBLIC FIXTURE for Sapient requirements-engine tests. Not a real
> protocol; all content is invented for testing. Constrained layout: operational
> statements appear as labeled lines (Dataset: / Population expression: /
> TEAE definition:), mirroring the structured layer real SAPs carry.

## 1 Background

This document describes the statistical methodology for protocol FX-001.
Efficacy is summarised in Table 14.2.1 and supporting listings. Subjects are
analysed as randomised. Nothing in this section defines an analysis dataset.

## 5.1 Analysis Populations

Dataset: ADSL
Population expression: SAFFL == "Y"

## 5.2 Per-Protocol Sensitivity Analyses

Dataset: ADSL
The per-protocol population comprises subjects who complete the planned
treatment period without major protocol deviations. Supportive summaries may
be produced for this group; the operational flag definition is not finalised
at this revision.

## 9.3 Treatment-Emergent Adverse Events

Dataset: ADAE
TEAE definition: TRTEMFL = if_else(AESTDT >= trt_start & AESTDT <= trt_start + 7, "Y", NA_character_)
Events outside the window are flagged as non-treatment-emergent.

## 9.4 Alternative Window Sensitivity Analysis

Dataset: ADAE
TEAE definition: TRTEMFL = if_else(AESTDT >= trt_start & AESTDT <= trt_start + 14, "Y", NA_character_)
This wider window is used only for the sensitivity summary.

## 10 Tumor Response

Dataset: ADRS
Best overall response must be derived per subject using sponsor function derive_best_overall_response_flag.

## 11 Tables, Listings and Figures

Output shells are maintained separately in the mock-up workbook.
