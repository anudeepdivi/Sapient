library(dplyr)

eff <- data.frame(
  USUBJID = c("S001", "S002", "S003", "S004"),
  ITTFL   = c("Y", "Y", "Y", "N"),
  COMPLFL = c("Y", "N", "Y", "Y"),
  PPFL    = c("Y", "Y", "N", "Y"),
  AVAL    = c(-3.2, -2.1, -4.0, -1.5)
)
pop <- eff %>% filter(ITTFL == "Y", COMPLFL == "Y")
cat("Sensitivity efficacy analysis records:", nrow(pop), "\n")
