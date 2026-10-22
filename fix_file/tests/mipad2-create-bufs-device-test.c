// SPDX-License-Identifier: GPL-2.0
/* No streaming. Caller requires camera idle and restores sensor geometry/controls.
 * This test keeps input unchanged and restores selected video format.
 */
#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/utsname.h>
#include <unistd.h>

static int release_buffers(int fd)
{
    struct v4l2_requestbuffers r={.type=V4L2_BUF_TYPE_VIDEO_CAPTURE,.memory=V4L2_MEMORY_MMAP};
    return ioctl(fd,VIDIOC_REQBUFS,&r);
}
static int create(int fd, const struct v4l2_format *fmt, unsigned size,
                  int expected_errno, const char *label)
{
    struct v4l2_create_buffers c={.count=1,.memory=V4L2_MEMORY_MMAP,.format=*fmt};
    c.format.fmt.pix.sizeimage=size;
    errno=0;
    int ret=ioctl(fd,VIDIOC_CREATE_BUFS,&c),error=errno;
    int failed=expected_errno ? ret!=-1 || error!=expected_errno : ret!=0 || c.count!=1;
    unsigned actual=0;
    if(!ret && c.count) {
        struct v4l2_buffer b={.type=fmt->type,.memory=V4L2_MEMORY_MMAP,.index=c.index};
        if(ioctl(fd,VIDIOC_QUERYBUF,&b)<0) failed=1;
        else { actual=b.length;if(actual<size)failed=1; }
    }
    printf("CASE %s requested=%u ret=%d errno=%d expected_errno=%d count=%u actual_length=%u %s\n",
           label,size,ret,error,expected_errno,c.count,actual,failed?"FAIL":"PASS");
    if(release_buffers(fd)<0) {perror("release buffers");return 1;}
    return failed;
}
int main(int argc,char **argv)
{
    struct utsname uts;
    if(argc!=2 || uname(&uts) ||
       (strcmp(uts.release,"6.14.0-mipad2-integrated-r10") &&
        strcmp(uts.release,"6.14.0-mipad2-integrated-r11") &&
        strcmp(uts.release,"6.14.0-mipad2-integrated-r12"))) {
        fprintf(stderr,"Usage: idle r10/r11/r12, %s /dev/videoN\n",argv[0]);return 2;
    }
    int fd=open(argv[1],O_RDWR|O_CLOEXEC),observer=-1,result=1;
    bool saved=false;
    struct v4l2_format original={.type=V4L2_BUF_TYPE_VIDEO_CAPTURE};
    if(fd<0) {perror("open");return 1;}
    struct v4l2_capability caps;
    if(ioctl(fd,VIDIOC_QUERYCAP,&caps)<0 || strcmp((char *)caps.driver,"atomisp")) goto out;
    if(ioctl(fd,VIDIOC_G_FMT,&original)<0) goto out;
    saved=true;
    struct v4l2_format current=original;
    current.fmt.pix.width=1280;current.fmt.pix.height=720;
    current.fmt.pix.pixelformat=V4L2_PIX_FMT_YUV420;
    if(ioctl(fd,VIDIOC_S_FMT,&current)<0) goto out;
    unsigned size=current.fmt.pix.sizeimage;
    if(!size || size>16*1024*1024) {errno=EINVAL;goto out;}
    printf("FORMAT %ux%u sizeimage=%u\n",current.fmt.pix.width,current.fmt.pix.height,size);
    result=0;
    result|=create(fd,&current,0,EINVAL,"zero");
    result|=create(fd,&current,size/2,EINVAL,"half");
    result|=create(fd,&current,size-1,EINVAL,"one-byte-short");
    result|=create(fd,&current,size,0,"exact");
    result|=create(fd,&current,size+1,0,"one-byte-extra");
    result|=create(fd,&current,size+1024*1024,0,"large");
    struct v4l2_create_buffers own={.count=1,.memory=V4L2_MEMORY_MMAP,.format=current};
    if(ioctl(fd,VIDIOC_CREATE_BUFS,&own)<0) {perror("owner create");result=1;goto out;}
    observer=open(argv[1],O_RDWR|O_CLOEXEC);
    if(observer<0) {result=1;goto out;}
    errno=0;
    int ret=ioctl(observer,VIDIOC_CREATE_BUFS,&own),error=errno;
    printf("NONOWNER ret=%d errno=%d expected_errno=%d\n",ret,error,EBUSY);
    if(ret!=-1 || error!=EBUSY)result=1;
out:
    if(observer>=0)close(observer);
    if(release_buffers(fd)<0)result=1;
    if(saved) {
        if(ioctl(fd,VIDIOC_S_FMT,&original)<0) {perror("restore format");result=1;}
        struct v4l2_format actual={.type=original.type};
        if(ioctl(fd,VIDIOC_G_FMT,&actual)<0 || actual.fmt.pix.width!=original.fmt.pix.width ||
           actual.fmt.pix.height!=original.fmt.pix.height || actual.fmt.pix.pixelformat!=original.fmt.pix.pixelformat ||
           actual.fmt.pix.sizeimage!=original.fmt.pix.sizeimage) {fprintf(stderr,"restore readback mismatch\n");result=1;}
    }
    close(fd);
    puts(result?"FAIL CREATE_BUFS contract":"PASS CREATE_BUFS contract");
    return result;
}
