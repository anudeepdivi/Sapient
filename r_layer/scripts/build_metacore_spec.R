library(metacore)

mc <- define_to_metacore("specs/define/adam_define.xml")
save_metacore(mc, "specs/metacore_spec.rds")
cat("SUCCESS: metacore spec saved to specs/metacore_spec.rds\n")
