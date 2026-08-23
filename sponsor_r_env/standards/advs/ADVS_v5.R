library(dplyr)

advs <- data.frame(
  USUBJID = c("S001", "S001", "S002", "S003"),
  SAFFL   = c("Y", "Y", "Y", "N"),
  AVISITN = c(1, 2, 1, 1),
  AVAL    = c(120, 125, 130, 140),
  BASE    = c(120, 120, 128, 135)
)
pop <- filter(advs, SAFFL == "Y")
res <- pop %>%
  mutate(CHG = AVAL - BASE) %>%
  arrange(USUBJID, AVISITN)
cat("Vital-sign change records (v5):", nrow(res), "\n")
