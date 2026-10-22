/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Support for Medifield PNW Camera Imaging ISP subsystem.
 *
 * Copyright (c) 2010 Intel Corporation. All Rights Reserved.
 *
 * Copyright (c) 2010 Silicon Hive www.siliconhive.com.
 */

#ifndef	__ATOMISP_FOPS_H__
#define	__ATOMISP_FOPS_H__
#include "atomisp_subdev.h"

struct atomisp_metadata_record {
	struct atomisp_frame_metadata frame;
	bool valid;
};

struct atomisp_fh {
	/* Must be first: v4l2_fh_release() frees this allocation. */
	struct v4l2_fh fh;
	/* Protect the per-handle snapshot, without taking the queue/ISP locks. */
	spinlock_t metadata_lock;
	u32 metadata_mode;
	struct atomisp_metadata_record metadata[VIDEO_MAX_FRAME];
};

static inline struct atomisp_fh *atomisp_to_fh(void *fh)
{
	return container_of(fh, struct atomisp_fh, fh);
}

/*
 * Memory help functions for image frame and private parameters
 */

int atomisp_qbuffers_to_css(struct atomisp_sub_device *asd);

extern const struct vb2_ops atomisp_vb2_ops;
extern const struct v4l2_file_operations atomisp_fops;

#endif /* __ATOMISP_FOPS_H__ */
