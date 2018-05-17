
/**
   Simplest possible task distributor
 */

#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MODE_VANILLA    0 // No Tcl
#define MODE_TCL_LINK   1 // Link/init but nothing else
#define MODE_TCL_EXEC   2 // Use Tcl exec
#define MODE_TCL_SYSTEM 3 // Use Tcl extension for system()

#if MODE == 1
#include <tcl.h>
#endif

#include <mpi.h>

static int rank, size;

#define buffer_size 1024
char buffer[buffer_size];

static const char* GET  = "GET";
static const char* STOP = "STOP";

static void check(bool condition, const char* format, ...);
static void fail(const char* format, va_list va);

static void master(int n, int workers);
static void worker(void);

static void tcl_start(const char* program);

int
main(int argc, char* argv[])
{
  MPI_Init(0, 0);

  double start = MPI_Wtime();

  MPI_Comm_rank(MPI_COMM_WORLD, &rank);
  MPI_Comm_size(MPI_COMM_WORLD, &size);

  check(argc == 2, "Requires task count!");

  int n;
  int c = sscanf(argv[1], "%i", &n);
  check(c == 1, "Could not parse as integer: %s", argv[1]);

  memset(buffer, 0, buffer_size);

  if (rank == 0)
  {
    printf("MODE: %i\n", MODE);
    printf("SIZE:  %i\n", size);
    printf("TASKS: %i\n", n);
  }
  int workers = size-1;
  
  tcl_start(argv[0]);
  
  if (rank == 0)
    master(n, workers);
  else
    worker();

  double stop = MPI_Wtime();
  if (rank == 0)
    printf("TIME: %0.3f\n", stop-start);

  MPI_Finalize();
  return 0;
}

void
master(int n, int workers)
{
  check(workers > 0, "No workers!");
  
  MPI_Status status;
  for (int i = 0; i < n; i++)
  {
    MPI_Recv(buffer, buffer_size, MPI_BYTE, MPI_ANY_SOURCE,
             0, MPI_COMM_WORLD, &status);
    strcpy(buffer, "bash -c 'exit 0'");
    int worker = status.MPI_SOURCE;
    MPI_Send(buffer, buffer_size, MPI_BYTE, worker,
             0, MPI_COMM_WORLD);
  }
  for (int i = 0; i < workers; i++)
  {
    MPI_Recv(buffer, buffer_size, MPI_BYTE, MPI_ANY_SOURCE,
             0, MPI_COMM_WORLD, &status);
    strcpy(buffer, STOP);
    int worker = status.MPI_SOURCE;
    MPI_Send(buffer, buffer_size, MPI_BYTE, worker,
             0, MPI_COMM_WORLD);
  }
}

void
worker()
{
  int count = 0;
  MPI_Status status;
  while (true)
  {
    strcpy(buffer, GET);
    MPI_Send(buffer, buffer_size, MPI_BYTE, 0, 0, MPI_COMM_WORLD);
    MPI_Recv(buffer, buffer_size, MPI_BYTE, 0, 0, MPI_COMM_WORLD,
             &status);
    if (strcmp(buffer, STOP) == 0)
      break;
    int rc = system(buffer);
    if (rc != 0)
      printf("command failed on rank: %i : %s\n", rank, buffer);
    count++;
  }
  // printf("worker rank: %i : tasks: %i\n", rank, count);
}

static void
check(bool condition, const char* format, ...)
{
  if (condition) return;

  va_list va;
  va_start(va, format);
  fail(format, va);
  va_end(va);
}

static void
fail(const char* format, va_list va)
{
  if (rank == 0)
  {
    vprintf(format, va);
    printf("\n");
  }
  exit(EXIT_FAILURE);
}

static
void tcl_start(const char* program)

#if MODE == MODE_VANILLA
// No Tcl
{}
#else
{
  Tcl_FindExecutable(program);
  Tcl_Interp* interp = Tcl_CreateInterp();
  int rc = Tcl_Init(interp);
  check(rc == TCL_OK, "Tcl_Init failed!");
}
#endif

static
void tcl_finalize()
#if MODE == MODE_VANILLA
// No Tcl
{}
#else
{
  Tcl_Finalize();
}
#endif

#if 0
const int buffer_size = 1024;
char buffer[buffer_size];

#define assert_msg(condition, format, args...)  \
    { if (!(condition))                          \
       assert_msg_impl(format, ## args);        \
    }

/**
   We bundle everything into one big printf for MPI
 */
void
assert_msg_impl(const char* format, ...)
{
  char buffer[buffer_size];
  int count = 0;
  char* p = &buffer[0];
  va_list ap;
  va_start(ap, format);
  count += sprintf(p, "error: ");
  count += vsnprintf(buffer+count, (size_t)(buffer_size-count), format, ap);
  va_end(ap);
  printf("%s\n", buffer);
  fflush(NULL);
  exit(EXIT_FAILURE);
}
#endif
