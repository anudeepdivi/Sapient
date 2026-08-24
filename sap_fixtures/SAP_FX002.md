# Statistical Analysis Plan — Protocol FX-002

> SYNTHETIC PUBLIC FIXTURE #2 for Sapient analysis-obligation tests. Not a
> real protocol. Constrained prose: obligation-bearing sentences use plain
> declarative forms so deterministic rules can harvest them; the ambiguity
> and conflict cases are planted deliberately.

## 2 Objectives and Endpoints

The primary endpoint is change from baseline in systolic blood pressure at Week 12.
Secondary endpoints include diastolic blood pressure change and the 24-hour ambulatory monitoring profile.

## 4 Treatments

Subjects are randomised in equal proportions to two treatment groups, Active and Placebo.

## 6.1 Primary Efficacy Analysis

The primary comparison is the difference between treatment groups in the primary endpoint at Week 12, analysed using ANCOVA adjusted for baseline value and centre.
The analysis population for this comparison is the full analysis population.
Subgroup summaries are produced by age group and by sex.
Additional supportive analyses may be performed as appropriate.

## 6.3 Protocol Amendment Note

Following the amendment, the primary analysis is based on a mixed model for repeated measurements.

## 6.2 Sensitivity Analyses

A sensitivity analysis of the primary endpoint excluding centre adjustment will be performed.

## 8 Safety Analyses

Treatment-emergent adverse events are summarised by treatment group for the safety population.
Dataset: ADAE
TEAE definition: TRTEMFL = if_else(AESTDT >= trt_start & AESTDT <= trt_start + 10, "Y", NA_character_)

## 12 Presentation of Results

Continuous endpoints are summarised descriptively by visit and treatment group.
The primary efficacy result is presented in a table.

## 13 Appendix

Numbered listings referenced in this plan are maintained in a separate external workbook.
