derive_population <- function(data, expr) {
  data %>% filter(!!rlang::parse_expr(expr))
}
