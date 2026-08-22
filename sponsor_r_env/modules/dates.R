derive_study_day <- function(data) {
  data %>% mutate(STUDYDAY = as.integer(TRTEDT - TRTSDT) + 1L)
}
