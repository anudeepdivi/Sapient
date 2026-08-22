library(dplyr)
source("modules/teae.R")

adae <- data.frame(
  USUBJID = c("S001", "S001", "S002", "S003", "S002"),
  AETERM  = c("Headache", "Nausea", "Fatigue", "Dizziness", "Rash"),
  AESTDT  = as.Date(c("2024-01-10", "2024-02-01", "2024-01-20",
                      "2024-02-15", "2023-12-28")),
  AESEV   = c("MILD", "MODERATE", "MILD", "SEVERE", "MILD")
)
adsl <- data.frame(
  USUBJID   = c("S001", "S002", "S003"),
  TRTSDT    = as.Date(c("2024-01-05", "2024-01-08", "2024-02-11")),
  SAFFL     = c("Y", "Y", "N"),
  SPECIALFL = c("N", "Y", "N")
)

ae1 <- derive_teae(adae, adsl$TRTSDT[match(adae$USUBJID, adsl$USUBJID)])
ae1 <- inner_join(ae1, select(adsl, USUBJID, SAFFL, SPECIALFL), by = "USUBJID")
ae1 <- filter(ae1, SAFFL == "Y")
cat("Treatment-emergent AEs:", sum(ae1$TRTEMFL == "Y", na.rm = TRUE), "\n")
print(count(ae1, AESEV))

out_path <- Sys.getenv("SAPIENT_STD_OUTPUT", "data/output/ADAE_v2.rds")
dir.create(dirname(out_path), showWarnings = FALSE, recursive = TRUE)
saveRDS(ae1, out_path)
