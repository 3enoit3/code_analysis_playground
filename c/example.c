// Functions
bool c_true() {
    return true;
}

bool c_call() {
    return c_true();
}

// Structures
struct c_struct {
    bool true_field = true;
};

bool c_use_struct() {
    c_struct a;
    a.true_field = false;
    return c_struct().true_field;
}

bool c_use_struct2(c_struct* p) {
    return p->true_field;
}

// Globals
bool c_global_var = true;
c_struct c_struct_var;

bool c_global() {
    c_struct_var.true_field;
    return c_global_var;
}

// Unkown
bool c_unknown() {
    c_unknown_true();
    c_unknown_struct.c_true_field;
    return c_unknown_global;
}
