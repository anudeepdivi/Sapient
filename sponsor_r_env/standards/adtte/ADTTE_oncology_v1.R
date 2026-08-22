library(dplyr)

tte <- data.frame(
  USUBJID = c("S001", "S002", "S003", "S004"),
  ITTFL   = c("Y", "Y", "Y", "N"),
  PFSFL   = c(1, 0, 1, 1),
  AVAL    = c(120, 200, 45, 90)
)
pop <- tte %>% filter(ITTFL == "Y")
cat("Median PFS (oncology):", median(pop$AVAL), "\n")
