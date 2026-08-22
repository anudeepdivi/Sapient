derive_treatment <- function(data) {
  data %>% mutate(TRT01P = ARM)
}
