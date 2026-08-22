derive_best_response_flag <- function(data, response_col = "AVALC") {
  data %>% mutate(BESTRSPFL = if_else(.data[[response_col]] %in% c("CR", "PR"), "Y", NA_character_))
}
