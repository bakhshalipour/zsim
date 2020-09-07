#include <iostream>
#include <stdint.h>

#define ITERATIONS (1<<31)
#define SIZE (4*1024*1024)  // > LLC size

using namespace std;

uint8_t* data;

extern "C"
int func(uint32_t index) {
    return data[index];
}

int main() {
    data = new uint8_t[SIZE]();

    volatile uint32_t var = 0;

    for (uint32_t i = 0; i < ITERATIONS; i++) {
        var += func(i % SIZE);
    }

    std::cout << "var = " << var << std::endl;

    return 0;
}
