args <- commandArgs(trailingOnly = TRUE)
program_path <- args[1]
dataset_name <- args[2]
if (length(args) < 4) stop("Explicit attempt output and parent input directories required")
adam_dir <- args[3]
adam_input_dir <- args[4]
Sys.setenv(SAPIENT_ADAM_DIR = adam_dir, SAPIENT_ADAM_INPUT_DIR = adam_input_dir)

tryCatch({
  output_path <- file.path(adam_dir, paste0(dataset_name, ".xpt"))
  if (file.exists(output_path)) stop("Attempt output must not already exist")
  source(program_path)
  if (!file.exists(output_path)) stop(sprintf("Expected output not written: %s", output_path))
  haven::read_xpt(output_path)
  cat(sprintf("SUCCESS: %s executed and saved to %s\n", dataset_name, output_path))
}, error = function(e) {
  cat(sprintf("ERROR: %s\n", conditionMessage(e)))
  quit(status = 1)
})