# PyDesk Image Compressor

First-party offline JPEG, PNG and WebP batch compression for PyDeskTools.
Original files are never overwritten. Compressed files are saved beside each
source image with a `-compressed` suffix, so starting a batch never interrupts
the workflow with an output-folder prompt.

`import_images` accepts an optional `paths` array for host drag-and-drop and
returns valid files together with structured rejections. The desktop workflow
only submits pending or retryable items; completed items are not compressed
again unless the user changes a compression setting.
