
/*++
Copyright (c) 2015 Microsoft Corporation

--*/

#include<vector>
#include"z3++.h"

using namespace z3;




/**
   Demonstration of how Z3 can be used to prove validity of
   De Morgan's Duality Law: {e not(x and y) <-> (not x) or ( not y) }
*/
void demorgan() {
    std::cout << "de-Morgan example\n";
    
    context c;

    expr x = c.bool_const("x");
    expr y = c.bool_const("y");
    expr conjecture = (!(x && y)) == (!x || !y);
    
    solver s(c);
    // adding the negation of the conjecture as a constraint.
    s.add(!conjecture);
    std::cout << s << "\n";
    std::cout << s.to_smt2() << "\n";
    switch (s.check()) {
    case unsat:   std::cout << "de-Morgan is valid\n"; break;
    case sat:     std::cout << "de-Morgan is not valid\n"; break;
    case unknown: std::cout << "unknown\n"; break;
    }
}

bool is_concrete_byte(context &c, expr byte) {

    assert(byte.length() == 8);
    
    expr zero = c.bv_const(0, 8);

    return (zero == byte).simplify().is_true() ||
            (zero == byte).simplify().is_false();
                
}


int main() {

    context c;
    expr x = c.bv_const(0, 8);
    expr y = c.bv_const("val", 8);

    std::cout << is_concrete_byte(c, x) << std::endl;
    std::cout << is_concrete_byte(c, y) << std::endl;

    return 0;
}

