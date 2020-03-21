// Functions
int f_true() {
    return 0;
}

int f_call() {
    return f_true();
}

// Structures
struct s_parent; // early declaration

typedef struct s_true {
    int fd_true;
} s_true;

struct s_parent {
    s_true fd_struct;
    s_true* fd_ptr;
};

typedef struct s_parent s_parent;
typedef struct s_parent t_redefined;
typedef t_redefined t_re_redefined;

struct s_forward;
typedef struct s_forward t_forward;

int f_use_struct() {
    s_true a;
    a.fd_true = 1;

    s_parent b;
    b.fd_struct.fd_true = 1;

    s_parent c;
    c.fd_ptr->fd_true = 1;

    s_parent d;
    return d.fd_struct.fd_true;
}

int f_use_struct_as_val(s_parent p) {
    return p.fd_struct.fd_true;
}

int f_use_struct_as_ptr(s_parent* p) {
    return p->fd_ptr->fd_true;
}

// Globals
int g_true = 0;
s_parent g_struct;
s_parent* g_ptr;

int f_global() {
    g_struct.fd_struct.fd_true;
    g_ptr->fd_ptr->fd_true;
    return g_true;
}

// Unkown
int unknown() {
    unknown_f();
    unknown_s.fd_true;
    unknown_p->fd_true;
    return unknown_global;
}
