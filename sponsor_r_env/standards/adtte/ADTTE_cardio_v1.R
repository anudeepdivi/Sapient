library(dplyr)

tte <- data.frame(
  USUBJID = c("S001", "S002", "S003", "S004"),
  ITTFL   = c("Y", "Y", "Y", "N"),
  CVFL    = c(1, 0, 1, 1),
  AVAL    = c(300, 450, 120, 260)
)
pop <- tte %>% filter(ITTFL == "Y")
cat("Median event time (cardiology):", median(pop$AVAL), "\n")
