derive_teae <- function(ae, trt_start) {
  ae %>% mutate(TRTEMFL = if_else(AESTDT >= trt_start, "Y", NA_character_))
}
