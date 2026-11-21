#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Exercise the exact u_serial console lifetime code with a stub USB controller."""

import os
from pathlib import Path
import shlex
import subprocess
import tempfile


root = Path(__file__).resolve().parents[2]
source = (root / "drivers/usb/gadget/function/u_serial.c").read_text()
types = source.split("/* console info */\n", 1)[1].split("/*\n * The port structure", 1)[0]
code = source.split("static struct tty_driver *gs_tty_driver;", 1)[1]
code = code.split("#ifdef CONFIG_U_SERIAL_CONSOLE\n", 1)[1]
code = code.split("ssize_t gserial_set_console(", 1)[0]

stubs = r"""
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define container_of(ptr, type, member) \
 ((type *)((char *)(ptr) - offsetof(type, member)))
#define GFP_ATOMIC 0
#define GFP_KERNEL 0
#define GS_CONSOLE_BUF_SIZE 8192
#define CON_PRINTBUFFER 1
#define pr_debug(...) ((void)0)
#define pr_warn(...) do { if (0) fprintf(stderr, __VA_ARGS__); } while (0)
#define pr_err(...) ((void)0)
#define strscpy(dest, src) strcpy(dest, src)
#define kzalloc_obj(obj, ...) calloc(1, sizeof(obj))
#define kfree(obj) free(obj)

typedef int spinlock_t;
static void spin_lock(spinlock_t *lock) { assert(!*lock); *lock = 1; }
static void spin_unlock(spinlock_t *lock) { assert(*lock == 1); *lock = 0; }
#define spin_lock_irq spin_lock
#define spin_unlock_irq spin_unlock
#define spin_lock_irqsave(lock, flags) ((flags) = 0, spin_lock(lock))
#define spin_unlock_irqrestore(lock, flags) ((void)(flags), spin_unlock(lock))
#define spin_lock_init(lock) (*(lock) = 0)
#define lockdep_assert_held(lock) assert(*(lock))
#define lockdep_assert_not_held(lock) assert(!*(lock))
struct kref { unsigned count; };
static void kref_init(struct kref *r) { r->count = 1; }
static void kref_get(struct kref *r) { assert(r->count); r->count++; }
static void kref_put(struct kref *r, void (*release)(struct kref *))
{
 assert(r->count);
 if (!--r->count)
  release(r);
}
struct console {
 char name[16];
 void (*write)(struct console *, const char *, unsigned);
 struct tty_driver *(*device)(struct console *, int *);
 int flags, index;
};
static struct tty_driver *gs_tty_driver;
static void register_console(struct console *c) { (void)c; }
static void unregister_console(struct console *c) { (void)c; }
struct work_struct {
 void (*callback)(struct work_struct *);
 bool scheduled;
};
#define INIT_WORK(work, cb) ((work)->callback = cb)
static void schedule_work(struct work_struct *w) { w->scheduled = true; }
static void cancel_work_sync(struct work_struct *w) { w->scheduled = false; }
struct kfifo { size_t size; };
static unsigned released_fifos;
static int kfifo_alloc(struct kfifo *fifo, size_t size, int flags)
{ (void)size; (void)flags; fifo->size = 0; return 0; }
static void kfifo_free(struct kfifo *fifo) { (void)fifo; released_fifos++; }
static size_t kfifo_out(struct kfifo *fifo, void *buf, size_t size)
{
 if (size > fifo->size)
  size = fifo->size;
 fifo->size -= size;
 memset(buf, 'x', size);
 return size;
}
static size_t kfifo_in(struct kfifo *fifo, const void *buf, size_t size)
{ (void)buf; fifo->size += size; return size; }
struct usb_ep;
struct usb_request {
 unsigned length;
 int status;
 void *buf, *context;
 void (*complete)(struct usb_ep *, struct usb_request *);
};
struct usb_ep {
 const char *name;
 unsigned maxpacket;
 struct usb_request *pending;
 bool reject, complete_first, detach_during_submit;
};
struct gserial { struct usb_ep *in; };
struct gs_port {
 struct gs_console *console;
 struct gserial *port_usb;
 spinlock_t port_lock, console_submit_lock;
 int port_num;
};
static unsigned allocations, frees, dequeues, submissions, givebacks;
static bool reject_alloc;
static struct usb_request *gs_alloc_req(struct usb_ep *ep, unsigned len, int flags)
{
 (void)ep; (void)flags;
 if (reject_alloc)
  return NULL;
 struct usb_request *req = calloc(1, sizeof(*req));
 assert(req);
 req->buf = malloc(len);
 assert(req->buf);
 allocations++;
 return req;
}
static void gs_free_req(struct usb_ep *ep, struct usb_request *req)
{
 assert(ep->pending != req);
 frees++;
 free(req->buf);
 free(req);
}
static void complete(struct usb_ep *ep, int status)
{
 struct usb_request *req = ep->pending;
 assert(req);
 ep->pending = NULL;
 req->status = status;
 givebacks++;
 req->complete(ep, req);
}
"""

operations = r"""
static void gs_console_disconnect(struct gs_port *port);

static int usb_ep_queue(struct usb_ep *ep, struct usb_request *req, int flags)
{
 struct gs_console_tx *tx = req->context;
 struct gs_port *port = tx->cons->port;
 (void)flags;
 assert(!ep->pending && tx->busy && req->length);
 assert(!tx->cons->lock && !port->port_lock && port->console_submit_lock);
 assert(tx->ref.count == 3);
 submissions++;
 if (ep->detach_during_submit) {
  spin_lock(&port->port_lock);
  gs_console_disconnect(port);
  spin_unlock(&port->port_lock);
  assert(!tx->cons->tx && tx->ref.count == 2);
 }
 if (ep->reject)
  return -ESHUTDOWN;
 ep->pending = req;
 if (ep->complete_first)
  complete(ep, 0); /* model a completion on another CPU before queue returns */
 return 0;
}
static int usb_ep_dequeue(struct usb_ep *ep, struct usb_request *req)
{
 assert(ep->pending == req);
 dequeues++;
 /* Leave ownership with the controller until the completion event. */
 return 0;
}
"""

scenarios = r"""
static void kick(struct gs_console *cons)
{
 cons->console.write(&cons->console, "hello", 5);
 assert(cons->work.scheduled);
 cons->work.scheduled = false;
 cons->work.callback(&cons->work);
}
static void detach(struct gs_port *p)
{
 spin_lock(&p->port_lock);
 gs_console_disconnect(p);
 spin_unlock(&p->port_lock);
 gs_console_sync_queue(p);
}
static void connect(struct gs_port *p)
{
 spin_lock(&p->port_lock);
 assert(gs_console_connect(p) == 0);
 spin_unlock(&p->port_lock);
}
int main(void)
{
 for (unsigned scenario = 0; scenario < 9; scenario++) {
  struct usb_ep ep = {.maxpacket = 64}, next = {.maxpacket = 64};
  struct gserial g = {.in = &ep};
  struct gs_port p = {.port_usb = &g};
  unsigned before_free = frees, before_fifo = released_fifos;
  unsigned before_dequeue = dequeues;
  reject_alloc = scenario == 7;
  assert(gs_console_init(&p) == 0);
  struct gs_console *cons = p.console;
  if (scenario == 7) {
   assert(!cons->tx);
   reject_alloc = false;
   connect(&p);
  }
  if (scenario == 0) {
   detach(&p); /* idle link: nothing to cancel */
   assert(!cons->tx && frees == before_free + 1);
  } else if (scenario == 1 || scenario == 6) {
   kick(cons);
   detach(&p); /* controller owns request until endpoint shutdown */
   assert(ep.pending && frees == before_free);
   if (scenario == 6) {
    g.in = &next;
    connect(&p);
    kick(cons);
    complete(&ep, 0);
    assert(!cons->work.scheduled && cons->tx->busy && next.pending);
    complete(&next, 0);
    assert(!cons->tx->busy);
   } else {
    complete(&ep, -ESHUTDOWN);
   }
   assert(frees == before_free + 1);
  } else if (scenario == 2) {
   kick(cons);
   gs_console_exit(&p); /* console-only stop: deferred cancellation */
   assert(!p.console && dequeues == before_dequeue + 1);
   assert(frees == before_free && released_fifos == before_fifo);
   complete(&ep, -ECONNRESET);
   assert(frees == before_free + 1 && released_fifos == before_fifo + 1);
  } else if (scenario == 3) {
   ep.reject = true;
   kick(cons);
   assert(!cons->tx->busy && cons->tx->ref.count == 1 && !ep.pending);
   ep.reject = false;
   kick(cons);
   complete(&ep, 0);
  } else if (scenario == 4) {
   ep.complete_first = true;
   kick(cons);
   assert(!cons->tx->busy && cons->tx->ref.count == 1);
  } else if (scenario == 8) {
   ep.detach_during_submit = true;
   kick(cons);
   gs_console_sync_queue(&p);
   assert(!cons->tx && frees == before_free);
   complete(&ep, -ESHUTDOWN);
   assert(frees == before_free + 1);
  } else {
   kick(cons);
   complete(&ep, -ESHUTDOWN);
   assert(!cons->tx->busy && !cons->work.scheduled);
  }
  gs_console_exit(&p);
  assert(!p.console && !ep.pending && !next.pending);
  assert(allocations == frees && released_fifos == before_fifo + 1);
  assert(dequeues == before_dequeue + (scenario == 2));
 }
 assert(dequeues == 1 && givebacks + 1 == submissions);
 puts("9 USB console lifetime cases passed");
 return 0;
}
"""

with tempfile.TemporaryDirectory(prefix="mipad2-usb-console-") as temp:
    cfile, binary = Path(temp) / "test.c", Path(temp) / "test"
    cfile.write_text(stubs + types + operations + code + scenarios)
    compiler = shlex.split(os.environ.get("CC", "cc"))
    subprocess.run(
        [*compiler, "-std=gnu11", "-O1", "-Wall", "-Wextra", "-Werror",
         str(cfile), "-o", str(binary)], check=True
    )
    subprocess.run([str(binary)], check=True)
