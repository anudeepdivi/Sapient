args <- commandArgs(trailingOnly = TRUE)
program_path <- args[1]
dataset_name <- args[2]

tryCatch({
  source(program_path)
  cat(sprintf("SUCCESS: %s executed and saved to data/adam/%s.xpt\n", dataset_name, dataset_name))
}, error = function(e) {
  cat(sprintf("ERROR: %s\n", conditionMessage(e)))
  quit(status = 1)
})